// Capture clearly labeled synthetic UI states; this is not a live-model test.
import {chromium} from 'playwright';
import {spawn} from 'node:child_process';
import {readFile,writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import net from 'node:net';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const identities=JSON.parse(await readFile(path.join(root,'local/lab-identities.json'),'utf8'));
const token=identities.actors.find(row=>row.id==='atlas-technician').token;
const listener=net.createServer();
await new Promise(resolve=>listener.listen(0,'127.0.0.1',resolve));
const port=listener.address().port;
await new Promise(resolve=>listener.close(resolve));
const origin=`http://127.0.0.1:${port}`;
const python=process.env.PRIVATE_TEST_PYTHON||path.join(root,process.platform==='win32'?'.venv/Scripts/python.exe':'.venv/bin/python');
const api=spawn(python,['-m','uvicorn','backend.main:load_app','--factory','--host','127.0.0.1','--port',String(port),'--no-access-log'],
 {cwd:root,env:{...process.env,PRIVATE_LAB_CONFIG:path.join(root,'local/lab-identities.json'),PRIVATE_OLLAMA_PROFILE:''},windowsHide:true,stdio:'ignore'});
const output=path.join(root,'docs/assets');
const document=JSON.parse(await readFile(path.join(root,'evaluation/development/manifest.json'),'utf8')).documents.find(row=>row.id==='atlas-backup-v1');
const source=document.pages[0].text;
const quote='Record the job ID and completion time.';
assert(source.includes(quote));
const fixtures={
 cited:{status:'sourced_excerpts',reason:'source_supported',excerpts:[{kind:'procedure',value:quote,
  evidence:{document_id:'atlas-backup-v1',version:1,page:1,quote}}],review_documents:[]},
 missing:{status:'abstain',reason:'no_authorized_current_source',excerpts:[],review_documents:[]},
 conflict:{status:'review',reason:'conflicting_current_sources',excerpts:[],review_documents:[
  {document_id:'atlas-retention-v1',version:1,reason:'conflicting_evidence'},
  {document_id:'atlas-retention-v2',version:1,reason:'conflicting_evidence'}]}
};
const browser=await chromium.launch({headless:true});
const page=await browser.newPage({viewport:{width:1280,height:900},deviceScaleFactor:1});
const outside=[],errors=[];
page.on('request',request=>{if(!request.url().startsWith(origin))outside.push(request.url())});
page.on('pageerror',error=>errors.push(error.message));
let state='cited';
await page.route('**/skills/answer_client_question',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(fixtures[state])}));

try{
 for(let attempt=0;attempt<100;attempt++){
  try{if((await fetch(origin+'/health')).ok)break;}catch{}
  if(attempt===99||api.exitCode!==null)throw Error('Memory harness did not start');
  await new Promise(resolve=>setTimeout(resolve,100));
 }
 await page.goto(origin+'/ui/');
 await page.getByLabel('Local access token').fill(token);
 await page.getByRole('button',{name:'Open workspace'}).click();
 await page.getByRole('heading',{name:'Source library'}).waitFor();
 await page.getByRole('navigation',{name:'Authorized sources'}).getByRole('button',{name:'atlas-backup-v1 Version 1'}).click();
 await page.getByRole('heading',{name:'atlas-backup-v1'}).waitFor();
 await page.evaluate(()=>{
  const banner=document.createElement('div');
  banner.textContent='SYNTHETIC UI REPLAY · validated Phase 8 response shape · no live inference in this capture';
  banner.style.cssText='background:#f5e8c5;color:#4b3814;padding:9px 32px;font:600 12px sans-serif;letter-spacing:.04em';
  document.body.prepend(banner);
 });
 for(const [key,question,heading] of [
  ['cited','What must be recorded during Atlas backup verification?','Cited excerpts'],
  ['missing','What is the monthly service fee?','No supported answer'],
  ['conflict','What is the backup retention period?','Needs source review']]){
  state=key;
  await page.getByLabel('Ask the local assistant').fill(question);
  await page.getByRole('button',{name:'Find cited excerpts'}).click();
  await page.getByRole('heading',{name:heading}).waitFor();
  if(key==='cited')assert.equal(await page.getByRole('button',{name:'atlas-backup-v1 · page 1 · v1'}).count(),1);
  if(key==='conflict')assert(await page.getByText('atlas-retention-v1 · v1',{exact:false}).count()>0);
  await page.screenshot({path:path.join(output,`fieldnote-${key}.png`),fullPage:true});
 }
 assert.deepEqual(errors,[]);
 assert.deepEqual(outside,[]);
 const hashes={};
 for(const key of Object.keys(fixtures)){
  const bytes=await readFile(path.join(output,`fieldnote-${key}.png`));
  hashes[`fieldnote-${key}.png`]=createHash('sha256').update(bytes).digest('hex');
 }
 await writeFile(path.join(root,'docs/evidence/ui-replay.json'),JSON.stringify({status:'passed',
  scope:'Synthetic UI fixture replay in built React/FastAPI memory harness; not live Ollama/Odoo acceptance',
  source_document:'evaluation/development/atlas-backup-v1.pdf',page:1,source_quote:quote,
  states:Object.keys(fixtures),nonlocal_browser_requests:outside.length,page_errors:errors.length,
  screenshot_sha256:hashes},null,2)+'\n');
 console.log(JSON.stringify({status:'passed',screenshots:Object.keys(hashes),nonlocal_browser_requests:outside.length}));
}finally{
 await browser.close();
 api.kill();
}
