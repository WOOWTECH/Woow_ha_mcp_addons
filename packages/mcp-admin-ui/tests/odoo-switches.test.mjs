import test from 'node:test';
import assert from 'node:assert/strict';
import {odooSwitches, odooSwitchPayload} from '../src/contracts.js';
import {AdminApi} from '../src/api.js';

const allOn = {enable_writes:true, allow_direct_writes:true, allow_unknown_methods:true, chatter_direct:true};
const base = '/api/hassio_ingress/DUMMY';
const bootstrap = {product:'odoo', odoo_write_switches:allOn, odoo_write_switches_source:'legacy_all_on'};

test('Odoo-only, exact four boolean switches; old API cannot be edited', () => {
  assert.deepEqual(odooSwitches(bootstrap), allOn);
  assert.deepEqual(odooSwitchPayload(bootstrap, {...allOn, chatter_direct:false}),
    {odoo_write_switches:{...allOn, chatter_direct:false}});
  for (const bad of [{...bootstrap, product:'hermes'}, {...bootstrap, odoo_write_switches_source:'unknown'},
    {...bootstrap, odoo_write_switches:{...allOn, extra:true}}, {...bootstrap, odoo_write_switches:{...allOn, enable_writes:1}},
    {...bootstrap, odoo_write_switches:{enable_writes:false}}]) {
    assert.equal(odooSwitches(bad), null);
    assert.throws(() => odooSwitchPayload(bad, allOn));
  }
  for (const bad of [{...allOn, chatter_direct:0}, {...allOn, extra:true}, {chatter_direct:false}])
    assert.throws(() => odooSwitchPayload(bootstrap, bad));
});

test('Odoo switch save refreshes CSRF and sends reviewed revision', async () => {
  const calls = [];
  const api = new AdminApi(base, async (url, options) => {
    calls.push({url, options});
    return new Response(JSON.stringify(url.endsWith('/bootstrap') ?
      {base_path:base, api_base:`${base}/api`, product:'odoo', csrf:'synthetic_csrf_1234567890'} : {saved:true}),
    {status:200});
  });
  await assert.rejects(() => api.mutate('odoo/write-switches', {odoo_write_switches:allOn}), /缺少設定版本/);
  await api.mutate('odoo/write-switches', {odoo_write_switches:allOn}, 'c1-' + 'a'.repeat(64));
  assert.equal(calls.at(-1).url, `${base}/api/odoo/write-switches`);
  assert.equal(calls.at(-1).options.method, 'PUT');
  assert.equal(calls.at(-1).options.headers['If-Match'], `"c1-${'a'.repeat(64)}"`);
  assert.deepEqual(JSON.parse(calls.at(-1).options.body), {odoo_write_switches:allOn});
});
