'use strict';
// Real pinned declarations, tools/call callback and test handler; fake execution.
// No server initialization or live backend. Network is forbidden even on drift.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
require('node:net').Socket.prototype.connect = () => { throw Error('network forbidden'); };
require('node:dgram').createSocket = () => { throw Error('network forbidden'); };
const root = process.argv[2];
const manager = require(path.join(root, 'tools-n8n-manager.js'));
const policy = require(path.join(root, 'tool-policy.js'));
const agents = require(path.join(root, 'agents-action-map.js'));
const names = ['n8n_manage_agents', 'n8n_test_workflow', 'n8n_list_catalog'];
const source = fs.readFileSync(path.join(root, 'server.js'), 'utf8');
const start = '        this.server.setRequestHandler(types_js_1.CallToolRequestSchema,';
const end = '        this.server.setRequestHandler(types_js_1.ListResourcesRequestSchema,';
assert.equal(source.split(start).length, 2);
assert.equal(source.split(end).length, 2);
const callback = source.slice(source.indexOf(start), source.indexOf(end));
const noop = () => {};
(async () => {
  const result = {};
  for (const name of names) {
    const selector = manager.TOOL_OPERATION_PARAM[name];
    const schema = manager.n8nManagementTools.find(t => t.name === name).inputSchema;
    const values = schema.properties[selector].enum;
    let dispatches = 0, call;
    const context = {
      types_js_1: {CallToolRequestSchema:'call'}, tools_n8n_manager_1:manager, tool_policy_1:policy,
      logger_1:{logger:{info:noop,warn:noop,debug:noop,error:noop}},
      telemetry_1:{telemetry:{trackToolUsage:noop,trackToolSequence:noop,trackError:noop}},
      redaction_1:{summarizeToolCallArgs:()=>({})}, ui_1:{isUIAppsEnabled:()=>false},
      instance_argument_1:{withoutInstanceArgument:args=>args}, additionalToolsByName:new Map(),
      server:{setRequestHandler:(_,handler)=>{call=handler;}}, getDisabledTools:()=>new Set(),
      getDisabledToolOperations:policy.getDisabledToolOperations,
      coerceStringifiedJsonParams:(_,args)=>args, sanitizeValidationResult:r=>r,
      executeTool:async()=>{dispatches++; return {success:true};},
    };
    vm.runInNewContext(callback,context,{timeout:1000});
    for (const op of values) {
      process.env.DISABLED_TOOL_OPERATIONS = `${name}:${op}`;
      const before = dispatches;
      const reply = await call({params:{name,arguments:{[selector]:op,workflowId:'fake'}}});
      assert.equal(reply.isError,true);
      assert.equal(dispatches,before);
      process.env.DISABLED_TOOL_OPERATIONS = '';
      assert.equal((await call({params:{name,arguments:{[selector]:op,workflowId:'fake'}}})).isError,undefined);
      assert.equal(dispatches,before+1);
    }
    result[name]={selector,values,default:manager.TOOL_OPERATION_DEFAULT[name]??schema.properties[selector].default??null,dispatches};
  }
  // Execute the whole pinned handler with real Zod, stopping at its native guard.
  const handlerSource = fs.readFileSync(path.join(root,'handlers-n8n-manager.js'),'utf8');
  const marker = 'async function handleTestWorkflow(';
  assert.equal(handlerSource.split(marker).length,2);
  const offset=handlerSource.indexOf(marker);
  const next=handlerSource.slice(offset+marker.length).search(/\n(?:async )?function /);
  assert(next>0);
  const handler=handlerSource.slice(offset,offset+marker.length+next);
  const schema=handlerSource.slice(handlerSource.indexOf('const testWorkflowSchema ='),handlerSource.indexOf('const listExecutionsSchema ='));
  const z=require(require.resolve('zod',{paths:[root]}));
  const ctx={zod_1:z,agents_action_map_1:agents,tool_policy_1:policy,
    optionalEmptyAware:s=>z.z.preprocess(v=>typeof v==='string'&&v.trim()===''?undefined:v,s.optional()),
    getN8nApiClient:()=>new Proxy({}, {get(){throw Error('backend forbidden');}}),
  };
  vm.runInNewContext(schema+'\n'+handler+'\nthis.testHandler=handleTestWorkflow;',ctx,{timeout:1000});
  process.env.DISABLED_TOOL_OPERATIONS='n8n_test_workflow:trigger';
  for(const method of [undefined,'auto','trigger',' \t\ufeff']) {
    const reply=await ctx.testHandler({workflowId:'fake',...(method===undefined?{}:{method})});
    assert.equal(reply.code,'OPERATION_DISABLED');
  }
  result.agentWrites=Object.fromEntries(Object.entries(agents.AGENT_ACTION_MAP).map(([op,entry])=>[op,entry.destructive]));
  process.stdout.write(JSON.stringify(result));
})().catch(error=>{console.error(error);process.exitCode=1;});
