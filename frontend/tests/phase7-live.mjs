import {chromium} from 'playwright';
import {readFile,writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import assert from 'node:assert/strict';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const origin='http://127.0.0.1:8077';
const identities=JSON.parse(await readFile(path.join(root,'local/phase-7/lab-identities.json'),'utf8'));
const token=id=>identities.actors.find(actor=>actor.id===id).token;
const id='atlas-browser-'+Date.now().toString(36);
const step='Record the job ID and completion time.';
const errors=[],outside=[];
const browser=await chromium.launch({headless:true});
const page=await browser.newPage({viewport:{width:1280,height:900}});
page.on('pageerror',error=>errors.push(error.message));
page.on('request',request=>{if(!request.url().startsWith(origin))outside.push(request.url())});

async function login(actor){
 await page.getByLabel('Local access token').fill(token(actor));
 await page.getByRole('button',{name:'Open workspace'}).click();
 await page.getByRole('heading',{name:'Source library'}).waitFor();
}
async function logout(){await page.getByRole('button',{name:'Sign out'}).click()}
function proposal(){return page.locator('.reviews article').filter({hasText:id}).last()}

try{
 await page.goto(origin+'/ui/');
 await login('atlas-technician');
 await page.getByText('Upload a PDF',{exact:true}).click();
 await page.getByLabel('PDF document ID').fill(id);
 await page.getByLabel('PDF title').fill('Phase 7 browser backup SOP');
 await page.getByLabel('PDF file').setInputFiles(path.join(root,'evaluation/development/atlas-backup-v1.pdf'));
 await page.getByRole('button',{name:'Upload and extract'}).click();
 await page.getByRole('status').filter({hasText:'PDF added'}).waitFor();
 await page.getByRole('heading',{name:'Phase 7 browser backup SOP'}).waitFor();
 await page.getByLabel('Search your sources').fill('job ID completion time');
 await page.getByRole('button',{name:'Search evidence'}).click();
 await page.getByRole('button',{name:new RegExp(id+' · page 1 · v1')}).waitFor();
 await page.getByLabel('Ask the local assistant').fill('What must be recorded during Atlas backup verification?');
 await page.getByRole('button',{name:'Find cited excerpts'}).click();
 await page.getByRole('heading',{name:'Cited excerpts'}).waitFor({timeout:150000});
 assert(await page.locator('.answer-results').getByText('job ID and completion time',{exact:false}).count()>0);
 await page.getByLabel('Checklist steps').fill(step);
 await page.getByRole('button',{name:'Prepare checklist'}).click();
 await page.getByRole('status').filter({hasText:'Checklist prepared'}).waitFor();
 await proposal().waitFor();
 await logout();

 await login('atlas-service_manager');
 await proposal().getByRole('button',{name:'Approve checklist'}).click();
 await page.getByRole('status').filter({hasText:'Checklist approved'}).waitFor();
 await proposal().getByRole('button',{name:'Review Odoo destination'}).click();
 await proposal().getByText('Odoo destination',{exact:false}).waitFor();
 await proposal().getByText('A different service manager must approve this destination.').waitFor();
 await logout();

 await login('atlas-reviewer');
 await proposal().getByRole('button',{name:'Review Odoo destination'}).click();
 await proposal().getByRole('button',{name:'Approve exact destination'}).click();
 await proposal().getByText('Status: approved').waitFor();
 await logout();

 await login('atlas-service_manager');
 await proposal().getByRole('button',{name:'Review Odoo destination'}).click();
 await proposal().getByRole('button',{name:'Save approved checklist to Odoo'}).click();
 await proposal().getByText('Saved and verified by Odoo read-back.',{exact:false}).waitFor({timeout:30000});
 const external=await proposal().locator('.odoo-preview').textContent();
 assert(/Odoo record \d+/.test(external));
 assert.equal(await proposal().getByRole('button',{name:'Save approved checklist to Odoo'}).count(),0);
 await page.screenshot({path:path.join(root,'local/phase-7/browser-odoo-review.png'),fullPage:true});
 await logout();

 await login('birch-technician');
 assert.equal(await page.getByRole('button',{name:'Phase 7 browser backup SOP Version 1'}).count(),0);
 assert.equal(await page.getByText(id,{exact:false}).count(),0);
 assert.deepEqual(errors,[]);
 assert.deepEqual(outside,[]);
 const evidence={status:'passed',profile:'real Chromium/React/FastAPI/Ollama/PostgreSQL/Odoo',
  document_id:id,pdf_uploaded:true,keyword_search:true,native_cited_answer:true,
  checklist_prepared:true,separate_checklist_and_destination_reviewers:true,
  odoo_readback_visible:true,save_button_removed_after_verification:true,
  birch_ui_cannot_see_atlas_source:true,page_errors:0,nonlocal_browser_requests:0,
  offline_tested:false,full_phase7_gate:false};
 await writeFile(path.join(root,'local/phase-7/browser-live.json'),JSON.stringify(evidence,null,2)+'\n');
 console.log(JSON.stringify(evidence));
}finally{await browser.close();}
