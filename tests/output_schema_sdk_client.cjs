// Pinned SDK 1.32.2 exercises actual AJV output validation after tools/list.
const {Client}=require(process.env.WOOW_SDK+'/dist/cjs/client/index.js');
const {StreamableHTTPClientTransport}=require(process.env.WOOW_SDK+'/dist/cjs/client/streamableHttp.js');
(async()=>{
 const transport=new StreamableHTTPClientTransport(new URL(process.env.WOOW_URL),{requestInit:{headers:{Authorization:'Bearer '+process.env.WOOW_TOKEN}}});
 const client=new Client({name:'output-schema-review',version:'0'});
 try{
  await client.connect(transport);
  const list=await client.listTools();const schemas=Object.fromEntries(list.tools.filter(t=>t.outputSchema).map(t=>[t.name,t.outputSchema]));
  const results=[];
  for(const [name,args,expectError] of JSON.parse(process.env.WOOW_CALLS)){
   const result=await client.callTool({name,arguments:args});
   if(Boolean(result.isError)!==expectError)throw new Error('unexpected tool result '+name);
   if(!expectError&&(!schemas[name]||!result.structuredContent))throw new Error('missing contract '+name);
   results.push({name,error:Boolean(result.isError),structured:result.structuredContent});
  }
  console.log(JSON.stringify({schemas,results,protocol:transport.protocolVersion}));
  await transport.terminateSession();
 }finally{await client.close();}
})().catch(e=>{console.error(e);process.exit(1);});
