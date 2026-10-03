// Explicit post-build check; no mock or test code enters dist.
import assert from 'node:assert/strict';
import {readFile,readdir,lstat} from 'node:fs/promises';
import {resolve,dirname} from 'node:path';
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
const css=await readFile(resolve(dist,'assets/app.css'),'utf8');
let references=0;
for (const [_,url] of css.matchAll(/url\("?([^"()]+)"?\)/g)) {
  assert(url.startsWith('./fonts/')&&!/[?#]/.test(url),'only content-hashed local query-free fonts');
  assert((await lstat(resolve(dist,'assets',url))).isFile()); references++;
}
for (const [target,source] of [
  ['poppins-OFL.txt','node_modules/@fontsource/poppins/LICENSE'],['outfit-OFL.txt','node_modules/@fontsource/outfit/LICENSE'],
  ['noto-sans-tc-OFL.txt','node_modules/@fontsource/noto-sans-tc/LICENSE'],['yellowtail-Apache-2.0.txt','node_modules/@fontsource/yellowtail/LICENSE'],
  ['mdi-LICENSE.txt','node_modules/@mdi/font/LICENSE'],['NOTICE.txt','NOTICE.txt'],
]) assert.deepEqual(await readFile(resolve(dist,'licenses',target)),await readFile(resolve(root,source)));
const js=await readFile(resolve(dist,'assets/app.js'),'utf8');
for (const marker of ['__fixture','LOCAL MOCK','localStorage','sessionStorage','INVENTED-LOCAL','make_ha_admin_verifier']) assert(!js.includes(marker));
assert(js.includes('woow-v3-exact-grants'));
assert((await readFile(resolve(dist,'index.html'),'utf8')).includes('__MCP_UI_BASE__'));
console.log(`PASS build closure: ${fonts} byte-identical fonts, ${references} local query-free references, 6 exact licenses/notices; no fixture/runtime bypass.`);
