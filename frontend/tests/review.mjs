import {chromium} from 'playwright';
import {spawn} from 'node:child_process';
import {readFile,mkdir,writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import net from 'node:net';
import assert from 'node:assert/strict';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const output=path.join(root,'local/phase-1');
await mkdir(output,{recursive:true});
const config=JSON.parse(await readFile(path.join(root,'local/lab-identities.json'),'utf8'));
const listener=net.createServer();
await new Promise(resolve=>listener.listen(0,'127.0.0.1',resolve));
const port=listener.address().port;
await new Promise(resolve=>listener.close(resolve));
const child=spawn(path.join(root,'.venv/Scripts/python.exe'),['-m','uvicorn','backend.main:load_app','--factory','--host','127.0.0.1','--port',String(port),'--no-access-log'],{cwd:root,env:{...process.env,PRIVATE_LAB_CONFIG:path.join(root,'local/lab-identities.json')},windowsHide:true,stdio:['ignore','pipe','pipe']});
let logs='';child.stdout.on('data',b=>logs+=b);child.stderr.on('data',b=>logs+=b);
let browser;
try{
 const origin=`http://127.0.0.1:${port}`;
 for(let attempt=0;;attempt++){
  try{const result=await fetch(origin+'/health');if(result.ok)break;}catch{}
  if(attempt>100||child.exitCode!==null)throw Error('API startup failed');
  await new Promise(resolve=>setTimeout(resolve,100));
 }
 browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const errors=[],outside=[];
 page.on('pageerror',e=>errors.push(e.message));
 page.on('request',r=>{if(!r.url().startsWith(origin))outside.push(r.url())});
 await page.goto(origin+'/ui/');
 async function login(id){const actor=config.actors.find(a=>a.id===id);await page.getByLabel('Local access token').fill(actor.token);await page.getByRole('button',{name:'Open workspace'}).click();await page.getByRole('heading',{name:'Source library'}).waitFor();await page.getByRole('button',{name:/Version 1/}).first().waitFor();}
 await login('atlas-technician'); await page.getByRole('heading',{name:'Sources to check'}).waitFor();
 await page.getByRole('button',{name:'atlas-backup-v1 Version 1',exact:true}).click();
 await page.getByLabel('Checklist steps',{exact:true}).fill('Open the local backup console.');
 await page.getByRole('button',{name:'Prepare checklist'}).click();
 await page.getByRole('status').filter({hasText:'Checklist prepared'}).waitFor();
 assert.equal(await page.getByRole('button',{name:'Approve checklist'}).count(),0);
 await page.screenshot({path:path.join(output,'review-desktop.png'),fullPage:true});
 await page.getByRole('button',{name:'Sign out'}).click();
 assert.equal(await page.getByText('Open the local backup console.',{exact:true}).count(),0);
 await login('atlas-service_manager');
 await page.getByRole('button',{name:'Approve checklist'}).click();
 await page.getByRole('status').filter({hasText:'Checklist approved'}).waitFor();
 await page.getByText('Approved for saving',{exact:false}).waitFor();
 await page.getByRole('button',{name:'Sign out'}).click();
 await login('birch-technician');
 assert.equal(await page.getByRole('button',{name:/atlas-/}).count(),0);
 assert.equal(await page.getByText('Open the local backup console.',{exact:true}).count(),0);
 await page.getByText('Add a text source',{exact:true}).click();
 await page.getByLabel('Document ID',{exact:true}).fill('browser-source');
 await page.getByLabel('Title',{exact:true}).fill('Browser smoke source');
 await page.getByLabel('Source text',{exact:true}).fill('Record the incident number.');
 await page.getByRole('button',{name:'Add source',exact:true}).click();
 await page.getByRole('status').filter({hasText:'Source added'}).waitFor();
 await page.getByRole('heading',{name:'Browser smoke source',exact:true}).waitFor();
 await page.getByText('Upload a PDF',{exact:true}).click();
 await page.getByLabel('PDF document ID',{exact:true}).fill('uploaded-sla');
 await page.getByLabel('PDF title',{exact:true}).fill('Uploaded service agreement');
 await page.getByLabel('PDF file',{exact:true}).setInputFiles(path.join(root,'evaluation/development/birch-sla-v1.pdf'));
 await page.getByRole('button',{name:'Upload and extract'}).click();
 await page.getByRole('status').filter({hasText:'PDF added'}).waitFor();
 await page.getByText('Page 2',{exact:true}).waitFor();
 await page.getByLabel('Search your sources',{exact:true}).fill('critical response');
 await page.getByRole('button',{name:'Search evidence'}).click();
 await page.getByRole('button',{name:'uploaded-sla · page 2 · v1',exact:true}).waitFor();
 await page.getByRole('button',{name:'uploaded-sla · page 2 · v1',exact:true}).click();
 await page.getByRole('heading',{name:'Uploaded service agreement',exact:true}).waitFor(); await page.getByLabel('Ask the local assistant').fill('What is the critical response target?'); await page.getByRole('button',{name:'Find cited excerpts'}).click(); await page.getByRole('alert').filter({hasText:'Local assistant unavailable'}).waitFor();
 await page.screenshot({path:path.join(root,'local/phase-2/pdf-search-desktop.png'),fullPage:true});
 await page.setViewportSize({width:390,height:844});
 await page.screenshot({path:path.join(output,'review-mobile.png'),fullPage:true});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth),false);
 // Revoke a displayed source using the real administrative API.
 const admin=config.actors.find(a=>a.id==='birch-administrator');
 async function revoke(identifier){
  const response=await fetch(origin+`/documents/${identifier}/access`,{method:'POST',headers:{Authorization:`Bearer ${admin.token}`,'Content-Type':'application/json'},body:JSON.stringify({actor_id:'birch-technician',revoked:true})});
  assert.equal(response.status,204);
 }
 await revoke('uploaded-sla');
 await page.getByRole('button',{name:'uploaded-sla · page 2 · v1',exact:true}).click();
 await page.getByRole('button',{name:'Open workspace'}).waitFor();
 assert.equal(await page.locator('.document-text,.search-results,.reviews').count(),0);
 await login('birch-technician');
 assert.equal(await page.getByRole('button',{name:'Uploaded service agreement Version 1',exact:true}).count(),0);
 await page.getByRole('button',{name:'Browser smoke source Version 1',exact:true}).click();
 await page.getByLabel('Checklist steps',{exact:true}).fill('Record the incident number.');
 await page.getByRole('button',{name:'Prepare checklist'}).click();
 await page.getByRole('status').filter({hasText:'Checklist prepared'}).waitFor();
 await page.getByLabel('Search your sources',{exact:true}).fill('incident number');
 await page.getByRole('button',{name:'Search evidence'}).click();
 await page.getByRole('button',{name:'browser-source · page 1 · v1',exact:true}).waitFor();
 await revoke('browser-source');
 await page.getByRole('button',{name:'Refresh',exact:true}).click();
 await page.getByRole('heading',{name:'Select a source',exact:true}).waitFor();
 assert.equal(await page.locator('.search-results').count(),0);
 await page.getByText('Prepared checklists will appear here.',{exact:true}).waitFor();
 assert.equal(await page.getByText('Record the incident number.',{exact:true}).count(),0);
 assert.deepEqual(errors,[]);assert.deepEqual(outside,[]);
 const result={status:'passed',checks:['real API and built React UI','authorized source-review queue','source selection and manual sourced checklist','separate actor approval','logout clears source state','two-tenant UI separation','text-source ingest','PDF upload and page provenance','keyword search and cited source navigation','local assistant unavailable state without hosted fallback','denied source access clears the mounted workspace','authorized refresh clears revoked source, search and review state','390px viewport without overflow','no page errors','no non-local browser requests observed'],limitations:['in-memory persistence','browser observation is not full-stack offline proof','PostgreSQL and Odoo acceptance pending']};
 await writeFile(path.join(output,'browser-review.json'),JSON.stringify(result,null,2));
 console.log(JSON.stringify(result));
}finally{if(browser)await browser.close();child.kill();await writeFile(path.join(output,'browser-server.log'),logs);}
