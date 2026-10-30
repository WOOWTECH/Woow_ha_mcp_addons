import test from 'node:test';
import assert from 'node:assert/strict';
import { AdminApi, ApiError } from '../src/api.js';
import { OperationIdentity } from '../src/operation-identity.js';

const revision = 'c1-' + 'a'.repeat(64);
const freshRevision = 'c1-' + 'b'.repeat(64);
const boot = {product:'n8n', base_path:'', api_base:'/api', csrf:'synthetic_csrf_value', configuration:{revision:freshRevision},
  operation_contract:{version:1, server_time_ms:1793318400000, retention_ms:86400000}};
export function memoryStorage() {
  const data = new Map();
  return {getItem:key=>data.get(key)??null, setItem:(key,value)=>data.set(key,value), removeItem:key=>data.delete(key)};
}
const receipt = (id, kind='token.rotate', replayed=false, state='completed') => ({id,kind,state,replayed});

test('every persistent operation requires reviewed revision; observations remain separate', async () => {
  for (const op of ['backend','backend/patch','policy','endpoint','n8n/session','odoo/write-switches','odoo/allowed-methods',
    'token/rotate','token/revoke','child/restart','owner-defaults/restore','owner-defaults/dismiss']) {
    const calls=[];
    const api=new AdminApi('',async path=>{calls.push(path);return Response.json(boot);},memoryStorage());
    await assert.rejects(()=>api.mutate(op,{}), /缺少設定版本/);
    assert.deepEqual(calls,['/api/bootstrap']);
  }
});

test('lost rotation response retains same ID and reviewed revision across page/API reload', async () => {
  const storage=memoryStorage(), writes=[];
  let effectCount=0;
  const fetcher=async(path, options)=>{
    if(path.endsWith('bootstrap')) return Response.json(boot);
    writes.push(options.headers);
    if(writes.length===1){effectCount++;throw Error('PRIVATE_NETWORK_CANARY');}
    return Response.json({status:'ok', operation:receipt(options.headers['Idempotency-Key'],'token.rotate',true)});
  };
  const first=new AdminApi('',fetcher,storage);
  await assert.rejects(()=>first.mutate('token/rotate',undefined,revision), /連線中斷/);
  const pending=first.pendingOperation();
  assert.equal(pending.revision,revision);
  assert.equal(pending.id.split('.')[0],String(boot.operation_contract.server_time_ms));
  assert.deepEqual(Object.keys(pending).sort(),['id','product','revision','route']);
  const second=new AdminApi('',fetcher,storage);
  const out=await second.retryOperation();
  assert.equal(out.operation.replayed,true);
  assert.equal(effectCount,1);
  assert.equal(writes[0]['Idempotency-Key'],writes[1]['Idempotency-Key']);
  assert.equal(writes[1]['If-Match'],`"${revision}"`);
  assert.equal(second.pendingOperation(),null);
});

test('receipt lookup is GET only, completed clears identity without disclosing secret', async () => {
  const storage=memoryStorage(), queries=[];
  const identity=new OperationIdentity('',storage);
  const pending=identity.start('token/revoke',revision,boot);
  const api=new AdminApi('',async(path, options)=>{
    queries.push({path,options});
    return Response.json({operation:receipt(pending.id,'token.revoke'),result:{token_state:'revoked'}});
  },storage);
  assert.equal((await api.queryOperation()).state,'completed');
  assert.equal(api.pendingOperation(),null);
  assert.equal(queries.length,1);
  assert.equal(queries[0].path,`/api/operations/${pending.id}`);
  assert.equal(queries[0].options.method,undefined);
});

test('unknown, expired, denied, malformed and foreign receipts retain retry identity', async () => {
  for(const response of [
    ()=>Response.json({detail:{code:'operation_outcome_unknown',error:'PRIVATE_CANARY'}},{status:409}),
    ()=>Response.json({detail:{code:'operation_id_expired'}},{status:410}),
    ()=>Response.json({detail:{code:'operation_not_found'}},{status:404}),
    ()=>Response.json({},{status:403}),
    ()=>Response.json({operation:receipt('foreign')}),
    ()=>Response.json({operation:receipt('foreign','mcp.restart')}),
  ]){
    const storage=memoryStorage(), identity=new OperationIdentity('',storage);
    const pending=identity.start('token/rotate',revision,boot);
    const api=new AdminApi('',async()=>response(),storage);
    await assert.rejects(()=>api.queryOperation(),e=>!e.message.includes('PRIVATE_CANARY'));
    assert.deepEqual(api.pendingOperation(),pending);
  }
});

test('unknown result cannot silently start different operation or change product',async()=>{
  const storage=memoryStorage(), identity=new OperationIdentity('',storage);
  identity.start('token/rotate',revision,boot);
  let writes=0;
  const api=new AdminApi('',async path=>{if(!path.endsWith('bootstrap'))writes++;return Response.json(boot);},storage);
  await assert.rejects(()=>api.mutate('child/restart',undefined,revision),/另一筆操作/);
  assert.throws(()=>identity.start('token/rotate',revision,{...boot,product:'odoo'}),/另一筆操作/);
  assert.equal(writes,0);
});

test('no storage, corrupt storage, refused storage and malformed bootstrap prevent effects',async()=>{
  const corrupt=memoryStorage();corrupt.setItem('woow-admin-operation-v1:','{"token":"PRIVATE_CANARY"}');
  for(const storage of [null,corrupt,{getItem:()=>null,setItem:()=>{throw Error();}}]){
    let writes=0;
    const api=new AdminApi('',async path=>{if(!path.endsWith('bootstrap'))writes++;return Response.json(boot);},storage);
    await assert.rejects(()=>api.mutate('token/rotate',undefined,revision),e=>!e.message.includes('PRIVATE_CANARY'));
    assert.equal(writes,0);
  }
  for(const contract of [undefined,{}, {version:1,server_time_ms:'bad'}]){
    const api=new AdminApi('',async()=>Response.json({...boot,operation_contract:contract}),memoryStorage());
    await assert.rejects(()=>api.mutate('token/rotate',undefined,revision),/缺少安全/);
  }
});

test('explicit pre-intent conflict releases ID; unknown outcome and disk failures do not',async()=>{
  for(const code of ['config_conflict','operation_outcome_unknown','operation_journal_unavailable']){
    let writes=0;
    const api=new AdminApi('',async path=>{
      if(path.endsWith('bootstrap'))return Response.json(boot);
      writes++;return Response.json({detail:{code}},{status:409});
    },memoryStorage());
    await assert.rejects(()=>api.mutate('token/rotate',undefined,revision),e=>e instanceof ApiError&&e.code===code);
    assert.equal(Boolean(api.pendingOperation()),code!=='config_conflict');assert.equal(writes,1);
  }
});
