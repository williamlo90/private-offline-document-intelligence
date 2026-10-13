import {Client} from '@modelcontextprotocol/sdk/client/index.js';
import {StdioClientTransport} from '@modelcontextprotocol/sdk/client/stdio.js';
import {readFile,writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import assert from 'node:assert/strict';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const identities=JSON.parse(await readFile(path.join(root,'local/phase-8/lab-identities.json'),'utf8'));
const actor=identities.actors.find(row=>row.id==='atlas-technician');
const transport=new StdioClientTransport({command:process.execPath,args:[path.join(root,'mcp/dist/server.js')],
 env:{PRIVATE_API_PORT:'8078',PRIVATE_API_TOKEN:actor.token},stderr:'pipe'});
const client=new Client({name:'phase8-offline-reference',version:'0.1.0'});
try{
 await client.connect(transport);
 const names=(await client.listTools()).tools.map(row=>row.name);
 assert(names.includes('private.answer_client_question'));
 const search=await client.callTool({name:'private.document_search',arguments:{query:'job ID completion time'}});
 assert(!search.isError);
 const hits=JSON.parse(search.content[0].text);
 assert(hits.some(row=>row.document_id.startsWith('atlas-')));
 const answer=await client.callTool({name:'private.answer_client_question',
  arguments:{question:'What must be recorded during Atlas backup verification?'}});
 assert(!answer.isError);
 const body=JSON.parse(answer.content[0].text);
 assert.equal(body.status,'sourced_excerpts');
 assert(body.excerpts.some(row=>row.value.includes('job ID and completion time')));
 const result={status:'passed',profile:'local MCP stdio -> loopback API -> offline Docker Ollama/PostgreSQL',
  tools_listed:names.length,authorized_search:true,native_sourced_answer:true,
  scope:'MCP read path on the same Phase 8 deployment; Odoo write through Phase 8 browser workflow'};
 await writeFile(path.join(root,'local/phase-8/mcp-live.json'),JSON.stringify(result,null,2)+'\n');
 console.log(JSON.stringify(result));
}finally{await client.close();}
