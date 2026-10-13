// Real MCP stdio, deliberately faulty HTTP adapter boundary (not Odoo/model evidence).
import {Client} from '@modelcontextprotocol/sdk/client/index.js';
import {StdioClientTransport} from '@modelcontextprotocol/sdk/client/stdio.js';
import http from 'node:http';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {mkdir,writeFile} from 'node:fs/promises';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
let mode='ok',hits=0,closed=0,redirectHits=0;
const api=http.createServer((req,res)=>{
 hits++;
 if(req.url==='/redirect-target'){redirectHits++;res.end('{}');return;}
 if(mode==='hang'){res.on('close',()=>closed++);return;}
 if(mode==='redirect'){res.writeHead(307,{Location:'/redirect-target'});res.end();return;}
 if(mode==='large'){res.end('x'.repeat(1000001));return;}
 if(mode==='malformed'){res.end('SECRET-internal-file-path');return;}
 if(mode==='unsafe_error'){res.writeHead(500);res.end(JSON.stringify({error:'SECRET-token'}));return;}
 res.setHeader('Content-Type','application/json');res.end('[]');
});
await new Promise(r=>api.listen(0,'127.0.0.1',r));
const transport=new StdioClientTransport({command:process.execPath,args:[path.join(root,'mcp/dist/server.js')],
 env:{PRIVATE_API_PORT:String(api.address().port),PRIVATE_API_TOKEN:'transport-fixture-token-0123456789',PRIVATE_API_TIMEOUT_MS:'500'},stderr:'pipe'});
let stderr='';
const client=new Client({name:'boundary-reference',version:'0.1.0'});
const request={name:'private.document_search',arguments:{query:'fixture'}};
const error=result=>JSON.parse(result.content[0].text).error;
try{
 await client.connect(transport);
 transport.stderr?.on('data',b=>stderr+=b);
 for(const scenario of ['redirect','large','malformed','unsafe_error']){
  mode=scenario;const before=hits;
  const result=await client.callTool(request);
  assert.equal(result.isError,true);
  assert.equal(error(result),scenario==='unsafe_error'?'request_failed':'local_request_failed');
  assert(!JSON.stringify(result).includes('SECRET'));assert.equal(hits,before+1);
 }
 assert.equal(redirectHits,0);
 mode='hang';
 assert.equal(error(await client.callTool(request)),'local_request_timeout');
 const beforeWrite=hits;
 const write=await client.callTool({name:'private.prepare_checklist',arguments:{document_ids:['sop'],expected_versions:{sop:1},steps:['Record ID.']}});
 assert.equal(error(write),'operation_outcome_unknown');assert.equal(hits,beforeWrite+1);
 const beforeSave=hits;
 const save=await client.callTool({name:'private.save_approved_checklist',arguments:{operation_id:'00000000-0000-4000-8000-000000000000'}});
 assert.equal(error(save),'operation_outcome_unknown');assert.equal(hits,beforeSave+1);
 const controller=new AbortController();
 const beforeCancel=hits;
 const pending=client.callTool(request,undefined,{signal:controller.signal});
 // Wait until the underlying HTTP request exists, then cancel through MCP.
 const deadline=Date.now()+2000;
 while(hits===beforeCancel&&Date.now()<deadline)await new Promise(r=>setTimeout(r,5));
 assert.equal(hits,beforeCancel+1);
 const closedBefore=closed;
 controller.abort();await assert.rejects(pending);
 while(closed===closedBefore&&Date.now()<deadline)await new Promise(r=>setTimeout(r,5));
 assert(closed>closedBefore,'MCP cancellation must close its HTTP request');
 mode='ok';assert.deepEqual(JSON.parse((await client.callTool(request)).content[0].text),[]);
 assert(!stderr.includes('SECRET')&&!stderr.includes('transport-fixture-token'));
 const result={status:'passed',checks:['redirect not followed','response size bound','malformed/error redaction','read deadline','draft/save unknown outcome without retry','SDK cancellation closes HTTP request','server usable after cancellation'],scope:'real stdio with faulty HTTP test double; no native inference/Odoo acceptance'};
 await mkdir(path.join(root,'local/phase-4'),{recursive:true});
 await writeFile(path.join(root,'local/phase-4/mcp-boundaries.json'),JSON.stringify(result,null,2));
 console.log(JSON.stringify(result));
}finally{await client.close();api.closeAllConnections();await new Promise(r=>api.close(r));}
