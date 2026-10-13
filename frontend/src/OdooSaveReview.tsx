import {useState} from 'react';
import {sessionFetch} from './session';

type Target={company_id:number;customer_id:number;opportunity_id:number;assignee_id:number};
type Operation={id:string;status:'review'|'approved'|'dispatched'|'unknown'|'verified';requested_by:string;approved_by:string|null;payload_hash:string;external_id:number|null;error:string|null;payload:{target:Target;steps:string[];source_versions:[string,number,string][];prepared_by:string}};

export function OdooSaveReview({proposalId,actorId,token,invalidate}:{proposalId:string;actorId:string;token:string;invalidate:()=>void}){
 const [operation,setOperation]=useState<Operation|null>(null);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 async function request(path:string,body?:unknown):Promise<Operation>{
  const response=await sessionFetch(token,invalidate,path,{method:'POST',headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
  const result=await response.json();
  if(!response.ok)throw Error(result.error==='save_coordinator_unavailable'?'Odoo is not connected in this local profile.':result.error==='save_payload_changed'?'Source or destination changed. Start a new review.':result.error==='save_approval_expired'?'Destination approval expired. Ask an administrator to review.':'Odoo review could not complete. Check the operation status before retrying.');
  return result;
 }
 async function run(work:()=>Promise<Operation>){setBusy(true);setError('');try{setOperation(await work())}catch(e){setError(e instanceof Error?e.message:'Odoo request failed.')}finally{setBusy(false)}}
 const canApprove=operation?.status==='review'&&actorId!==operation.requested_by&&actorId!==operation.payload.prepared_by;
 return <div className="odoo-review"><button className="quiet" disabled={busy} onClick={()=>void run(()=>request('/save-operations/prepare',{proposal_id:proposalId}))}>{operation?'Refresh Odoo review':'Review Odoo destination'}</button>
  {error&&<p role="alert" className="alert">{error}</p>}
  {operation&&<div className="odoo-preview"><p><strong>Odoo destination</strong> · company {operation.payload.target.company_id}, customer {operation.payload.target.customer_id}, opportunity {operation.payload.target.opportunity_id}, assignee {operation.payload.target.assignee_id}</p>
   <p className="reference">Exact payload hash: {operation.payload_hash}</p>
   <ol>{operation.payload.steps.map((step,i)=><li key={i}>{step}</li>)}</ol>
   {operation.payload.source_versions.map(([id,version])=><p className="reference" key={id}>{id} · v{version}</p>)}
   <p>Status: <strong>{operation.status}</strong>{operation.external_id?` · Odoo record ${operation.external_id}`:''}</p>
   {canApprove&&<button disabled={busy} onClick={()=>void run(()=>request(`/save-operations/${operation.id}/approve`,{payload_hash:operation.payload_hash}))}>Approve exact destination</button>}
   {operation.status==='review'&&!canApprove&&<p className="muted">A different service manager must approve this destination.</p>}
   {operation.status==='approved'&&<button disabled={busy} onClick={()=>void run(()=>request(`/save-operations/${operation.id}/dispatch`))}>Save approved checklist to Odoo</button>}
   {(operation.status==='unknown'||operation.status==='dispatched')&&<button disabled={busy} onClick={()=>void run(()=>request(`/save-operations/${operation.id}/verify`))}>Verify Odoo read-back</button>}
   {operation.status==='verified'&&<p className="notice">Saved and verified by Odoo read-back. This records planned work; it does not complete the IT task.</p>}
  </div>}
 </div>;
}
