import {McpServer} from '@modelcontextprotocol/sdk/server/mcp.js';
import {StdioServerTransport} from '@modelcontextprotocol/sdk/server/stdio.js';
import {z} from 'zod';

const port=Number(process.env.PRIVATE_API_PORT);
const token=process.env.PRIVATE_API_TOKEN;
const timeoutMs=Number(process.env.PRIVATE_API_TIMEOUT_MS??125000);
if(!Number.isInteger(port)||port<1024||port>65535||!token||token.length<24||!Number.isInteger(timeoutMs)||timeoutMs<50||timeoutMs>125000){
 process.stderr.write('Invalid local MCP configuration.\n');process.exit(1);
}
const origin=`http://127.0.0.1:${port}`;
const server=new McpServer({name:'private-documents',version:'0.1.0'});
const safeErrors=new Set(['forbidden','unauthenticated','document_not_found','source_changed_or_expired','source_requires_review','source_conflict','unsupported_step','invalid_input','native_model_unavailable','native_model_timeout','native_runtime_needs_recovery','resource_budget_unavailable','runtime_memory_reserve','inference_busy','invalid_model_output','invalid_model_evidence','native_model_pin_mismatch','save_coordinator_unavailable','operation_not_found','operation_not_dispatched','approved_checklist_required','destination_approval_required','save_approval_expired','save_payload_changed','self_approval','already_reviewed','odoo_target_unavailable','odoo_checklist_extension_required']);
function failure(code:string){return {isError:true,content:[{type:'text' as const,text:JSON.stringify({error:code})}]};}
async function api(path:string,body:unknown,signal:AbortSignal){
 const timeout=AbortSignal.timeout(timeoutMs);
 const response=await fetch(origin+path,{method:body===undefined?'GET':'POST',
  headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json'},
  body:body===undefined?undefined:JSON.stringify(body),redirect:'error',
  signal:AbortSignal.any([signal,timeout])});
 const reader=response.body?.getReader();if(!reader)throw Error('empty');
 const chunks:Uint8Array[]=[];let total=0;
 try{while(true){const {done,value}=await reader.read();if(done)break;total+=value.length;
  if(total>1_000_000)throw Error('response_limit');chunks.push(value);}}
 finally{await reader.cancel();}
 const result=JSON.parse(Buffer.concat(chunks).toString('utf8'));
 if(!response.ok)return failure(safeErrors.has(result.error)?result.error:'request_failed');
 return {content:[{type:'text' as const,text:JSON.stringify(result)}]};
}
const id=z.string().min(1).max(100);
const uuid=z.string().uuid();
const hash=z.string().regex(/^[0-9a-f]{64}$/);
function register(name:string,description:string,schema:z.ZodRawShape,path:(input:any)=>string,body:(input:any)=>unknown,readOnly=true){
 server.registerTool(name,{description,inputSchema:z.strictObject(schema),
  annotations:{readOnlyHint:readOnly,destructiveHint:false,idempotentHint:readOnly,openWorldHint:false}},
  async(input,extra)=>{try{return await api(path(input),body(input),extra.signal);}
  catch(error){return failure(!readOnly?'operation_outcome_unknown':extra.signal.aborted?'operation_cancelled':error instanceof Error&&error.name==='TimeoutError'?'local_request_timeout':'local_request_failed');}});
}
register('private.document_search','Search authorized source excerpts; matches are not answers.',{query:z.string().min(1).max(1000)},x=>'/search?q='+encodeURIComponent(x.query),()=>undefined);
register('private.extract_service_terms','Select cited service terms; native model may be unavailable.',{document_id:id,version:z.number().int().min(1)},()=>'/skills/extract_service_terms',x=>x);
register('private.answer_client_question','Return source selections, abstention or review; native model required for generation.',{question:z.string().min(1).max(1000)},()=>'/skills/answer_client_question',x=>x);
register('private.prepare_checklist','Create a review draft from exact source steps. Does not approve, save or execute work. Do not retry an unknown outcome without reviewing the queue.',
 {document_ids:z.array(id).min(1).max(10),steps:z.array(z.string().min(1).max(2000)).min(1).max(30),expected_versions:z.record(id,z.number().int().min(1))},()=>'/skills/prepare_service_checklist',x=>x,false);
register('private.runtime_health','Administrator-only bundle readiness inspection; does not prove offline operation.',{},()=>'/skills/audit_offline_readiness',()=>({}));
register('private.prepare_odoo_save','Create a destination-bound preview for an approved checklist; no Odoo write.',
 {proposal_id:uuid},()=>'/save-operations/prepare',x=>x,false);
register('private.inspect_save','Read the scoped save operation and full destination preview.',
 {operation_id:uuid},x=>'/save-operations/'+encodeURIComponent(x.operation_id),()=>undefined);
register('private.approve_odoo_target','A different service manager approves the exact destination-bound payload hash; this does not write to Odoo.',
 {operation_id:uuid,payload_hash:hash},x=>'/save-operations/'+encodeURIComponent(x.operation_id)+'/approve',x=>({payload_hash:x.payload_hash}),false);
register('private.save_approved_checklist','Dispatch an approved operation once; unknown outcomes require read-back, never blind retry. Saving a task does not complete its IT work.',
 {operation_id:uuid},x=>'/save-operations/'+encodeURIComponent(x.operation_id)+'/dispatch',()=>({}),false);
register('private.verify_save','Read back an operation after dispatch; no Odoo write or redispatch.',
 {operation_id:uuid},x=>'/save-operations/'+encodeURIComponent(x.operation_id)+'/verify',()=>({}));
await server.connect(new StdioServerTransport());
