import {Client} from '@modelcontextprotocol/sdk/client/index.js';
import {StdioClientTransport} from '@modelcontextprotocol/sdk/client/stdio.js';
import {spawn} from 'node:child_process';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import net from 'node:net';
import assert from 'node:assert/strict';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const identities=JSON.parse(await readFile(path.join(root,'local/lab-identities.json'),'utf8'));
const listener=net.createServer();await new Promise(r=>listener.listen(0,'127.0.0.1',r));
const port=listener.address().port;await new Promise(r=>listener.close(r));
const server=spawn(process.env.PRIVATE_TEST_PYTHON||path.join(root,'.venv/Scripts/python.exe'),['-m','uvicorn','backend.main:load_app','--factory','--host','127.0.0.1','--port',String(port),'--no-access-log'],
 {cwd:root,env:{...process.env,PRIVATE_LAB_CONFIG:path.join(root,'local/lab-identities.json'),PRIVATE_OLLAMA_PROFILE:''},windowsHide:true,stdio:'ignore'});
const origin=`http://127.0.0.1:${port}`;
let client,transport;
const actor=id=>identities.actors.find(a=>a.id===id);
async function connect(id){
 if(client)await client.close();
 transport=new StdioClientTransport({command:process.execPath,args:[path.join(root,'mcp/dist/server.js')],
  env:{PRIVATE_API_PORT:String(port),PRIVATE_API_TOKEN:actor(id).token},stderr:'pipe'});
 client=new Client({name:'private-reference-client',version:'0.1.0'});
 await client.connect(transport);
}
async function call(name,args){return client.callTool({name,arguments:args});}
const data=result=>JSON.parse(result.content[0].text);
try{
 for(let i=0;;i++){
  try{if((await fetch(origin+'/health')).ok)break;}catch{}
  if(i>100||server.exitCode!==null)throw Error('API startup failed');
  await new Promise(r=>setTimeout(r,100));
 }
 await connect('atlas-technician');
 const names=(await client.listTools()).tools.map(t=>t.name);
 assert.equal(names.length,10);
 assert(names.includes('private.save_approved_checklist'));
 const search=data(await call('private.document_search',{query:'backup'}));
 assert(search.length>0);assert(search.every(h=>h.document_id.startsWith('atlas-')));
 const missing=data(await call('private.answer_client_question',{question:'zznoevidencezz'}));
 assert.equal(missing.status,'abstain');
 const unavailable=await call('private.extract_service_terms',{document_id:'atlas-backup-v1',version:1});
 assert.equal(unavailable.isError,true);assert.equal(data(unavailable).error,'native_model_unavailable');
 assert.equal(data(await call('private.prepare_odoo_save',{proposal_id:'00000000-0000-4000-8000-000000000000'})).error,'save_coordinator_unavailable');
 const denied=await call('private.runtime_health',{});
 assert.equal(denied.isError,true);assert.equal(data(denied).error,'forbidden');
 const injected=await call('private.document_search',{query:'backup',tenant:'birch'});
 assert.equal(injected.isError,true);
 const prepared=data(await call('private.prepare_checklist',{document_ids:['atlas-backup-v1'],expected_versions:{'atlas-backup-v1':1},steps:['Open the local backup console.']}));
 assert.equal(prepared.status,'review');assert.equal(prepared.approver_id,null);
 const stale=await call('private.prepare_checklist',{document_ids:['atlas-backup-v1'],expected_versions:{'atlas-backup-v1':99},steps:['Open the local backup console.']});
 assert.equal(data(stale).error,'source_changed_or_expired');
 await connect('birch-technician');
 const wrong=await call('private.extract_service_terms',{document_id:'atlas-backup-v1',version:1});
 assert.equal(data(wrong).error,'document_not_found');
 const birch=data(await call('private.document_search',{query:'response'}));
 assert(birch.every(h=>h.document_id.startsWith('birch-')));
 await connect('atlas-administrator');
 const audit=data(await call('private.runtime_health',{}));
 assert.equal(audit.offline_validated,false);
 assert.equal(data(await call('private.document_search',{query:'backup'})).error,'forbidden');
 const result={status:'passed',transport:'real SDK stdio subprocess and native FastAPI memory harness',
  checks:['initialize/list/call','strict extra-field rejection','tenant separation','admin business-data denial','admin readiness','native-model-unavailable propagation','version-bound draft','stale version rejection','save tools fail closed without coordinator'],
  limitations:['no real model inference in this suite','no live Odoo','PostgreSQL acceptance pending']};
 await mkdir(path.join(root,'local/phase-4'),{recursive:true});
 await writeFile(process.env.PRIVATE_MCP_EVIDENCE||path.join(root,'local/phase-4/mcp-stdio.json'),JSON.stringify(result,null,2));
 console.log(JSON.stringify(result));
}finally{
 if(client)await client.close();
 server.kill();
}
