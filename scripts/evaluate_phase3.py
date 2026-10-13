"""Native local assistant development evaluation against the pre-model rubric."""
import hashlib
import json
from pathlib import Path
import sys
import time

from backend.assistant_contracts import Candidate, Extraction, Question
from backend.domain import Actor, DomainError, MemoryRepository, Service
from backend.ollama_adapter import OllamaGenerator, OllamaProfile, PROMPT_SHA256
from backend.resources import available_memory_bytes
from backend.pdf_parser import parse_pdf
from backend.skills import BusinessSkills

root=Path(__file__).resolve().parents[1]
folder=root/'evaluation/development'
profile=OllamaProfile.model_validate_json(Path(sys.argv[1]).read_bytes())
manifest_bytes=(folder/'manifest.json').read_bytes()
expected_bytes=(folder/'expected.json').read_bytes()
manifest=json.loads(manifest_bytes)
expected=json.loads(expected_bytes)
rubric=json.loads((root/'evaluation/rubric-v1.json').read_text(encoding='utf-8'))
service=Service(MemoryRepository())
for item in manifest['documents']:
    data=(folder/item['file']).read_bytes()
    assert hashlib.sha256(data).hexdigest()==item['sha256']
    parsed=parse_pdf(data)
    service.ingest(Actor('evaluator',item['tenant'],'technician'),item['id'],item['id'],
                   '\n\n'.join(p.text for p in parsed.pages),pages=parsed.pages,source_hash=parsed.sha256,
                   effective=item['effective'],expires=item['expires'],family=item['family'])
out=root/'local/phase-3';out.mkdir(parents=True,exist_ok=True)
raw_path=out/'raw-model-selections.jsonl'
raw_path.write_text('',encoding='utf-8')
class RecordingGenerator:
    def __init__(self):self.native=OllamaGenerator(profile)
    def generate(self,task,payload,schema):
        result=self.native.generate(task,payload,schema)
        with raw_path.open('a',encoding='utf-8') as log:
            log.write(json.dumps({'task':task,'question':payload.get('question'),
                                  'evidence':payload.get('evidence'),'result':result},ensure_ascii=False)+'\n')
        return result
skills=BusinessSkills(service,root/'local/offline-bundle',RecordingGenerator())
rows=[];timings=[];answerable=0;completed=0;handling_total=0;handling_correct=0
citations=0;correct_citations=0;claims=0;supported_claims=0
disclosures=0
memory_wait_seconds=0.0

def wait_for_preflight_memory():
    """Queue lab work until the declared preflight can run; never lower it."""
    minimum=profile.minimum_free_ram_gib*1024**3
    started=time.monotonic()
    while available_memory_bytes()<minimum and time.monotonic()-started<60:
        time.sleep(1)
    return time.monotonic()-started

for case in expected['cases']:
    actor=Actor('evaluator',case['tenant'],'technician')
    memory_wait_seconds+=wait_for_preflight_memory()
    started=time.monotonic()
    try:
        result=skills.answer_client_question(actor,Question(question=case['question']))
        error=None
    except DomainError as exc:
        result=None;error=exc.code
    elapsed=time.monotonic()-started;timings.append(elapsed)
    refs={(doc,page) for doc,page,_ in case['evidence']}
    excerpts=[] if result is None else result.excerpts
    citation_results=[]
    for excerpt in excerpts:
        ref=excerpt.evidence
        document=service.read_version(actor,ref.document_id,ref.version)
        page=next(p for p in document.pages if p.number==ref.page)
        exact=(document.digest==excerpt.source_sha256 and page.text[ref.start:ref.end]==ref.quote==excerpt.value)
        relevant=(ref.document_id,ref.page) in refs
        citation_results.append({'exact':exact,'reference_location':relevant})
        citations+=1;correct_citations+=int(exact and relevant)
        claims+=1;supported_claims+=int(exact and relevant)
    text=' '.join(' '.join(e.value for e in excerpts).casefold().split())
    disclosures+=sum(int(' '.join(forbidden.casefold().split()) in text) for forbidden in case.get('forbidden',[]))
    required_present={value:' '.join(value.casefold().split()) in text for value in case['required']}
    if case['status'] in {'answered','draft'}:
        answerable+=1
        completed+=int(result is not None and result.status=='sourced_excerpts'
                       and all(required_present.values()) and bool(excerpts)
                       and all(x['exact'] and x['reference_location'] for x in citation_results))
    if case['status'] in {'missing','conflicting','expired'}:
        handling_total+=1
        expected_status='abstain' if case['status']=='missing' else 'review'
        handling_correct+=int(result is not None and result.status==expected_status)
    rows.append({'id':case['id'],'expected_status':case['status'],
                 'status':None if result is None else result.status,
                 'reason':None if result is None else result.reason,
                 'error':error,'seconds':round(elapsed,3),
                 'required_present':required_present,'citation_checks':citation_results,
                 'excerpts':[{'kind':e.kind,'value':e.value,'document_id':e.evidence.document_id,
                              'page':e.evidence.page,'version':e.evidence.version} for e in excerpts]})
extraction=json.loads((folder/'extraction-expected.json').read_text(encoding='utf-8'))
extraction_rows=[];fields_total=0;fields_correct=0;documents_correct=0
normalize=lambda text:' '.join(text.casefold().split())
for case in extraction['documents']:
    actor=Actor('evaluator',case['tenant'],'technician')
    document=service.read_document(actor,case['document_id'])
    memory_wait_seconds+=wait_for_preflight_memory()
    started=time.monotonic()
    try:
        result=skills.extract_service_terms(actor,Extraction(document_id=document.id,version=document.version))
        error=None
    except DomainError as exc:
        result=None;error=exc.code
    timings.append(time.monotonic()-started)
    excerpts=[] if result is None else result.excerpts
    checks=[]
    for field in case['fields']:
        correct=any(e.kind==field['kind'] and e.evidence.page==field['page'] and
                    e.evidence.document_id==case['document_id'] and
                    normalize(field['value']) in normalize(e.value) for e in excerpts)
        checks.append({'kind':field['kind'],'value':field['value'],'correct':correct})
        fields_total+=1;fields_correct+=int(correct)
    documents_correct+=int(bool(checks) and all(c['correct'] for c in checks))
    for excerpt in excerpts:
        ref=excerpt.evidence
        page=next(p for p in document.pages if p.number==ref.page)
        exact=(ref.document_id==document.id and ref.version==document.version and
               excerpt.source_sha256==document.digest and page.text[ref.start:ref.end]==ref.quote==excerpt.value)
        relevant=any(field['kind']==excerpt.kind and field['page']==ref.page and
                     normalize(field['value']) in normalize(excerpt.value) for field in case['fields'])
        citations+=1;correct_citations+=int(exact)
        claims+=1;supported_claims+=int(exact and relevant)
    extraction_rows.append({'document_id':document.id,'status':None if result is None else result.status,
                            'error':error,'fields':checks,'excerpt_count':len(excerpts)})
def quantile(p):
    ordered=sorted(timings)
    position=(len(ordered)-1)*p
    lower=int(position); upper=min(lower+1,len(ordered)-1)
    return round(ordered[lower]+(ordered[upper]-ordered[lower])*(position-lower),3)
report={'split':'development','native_inference':True,'cases':len(rows),
        'answerable_completion':{'passed':completed,'total':answerable},
        'field_correctness':{'correct':fields_correct,'total':fields_total},
        'document_all_required_fields_correct':{'correct':documents_correct,'total':len(extraction_rows)},
        'missing_conflicting_expired_handling':{'passed':handling_correct,'total':handling_total},
        'citation_correctness':{'correct':correct_citations,'total':citations},
        'supported_claim_precision':{'supported':supported_claims,'total':claims},
        'cross_client_disclosures':disclosures,
        'unauthorized_writes':len(service.repo.proposals('atlas'))+len(service.repo.proposals('birch')),
        'latency_seconds':{'p50':quantile(.5),'p90':quantile(.9),'p95':quantile(.95),'n':len(timings)},
        'total_task_seconds':round(sum(timings),3),
        'preflight_memory_queue_wait_seconds':round(memory_wait_seconds,3),
        'tasks_per_minute':round(60*len(timings)/sum(timings),3) if sum(timings) else None,
        'model':profile.model,'model_digest':profile.digest,'prompt_sha256':PROMPT_SHA256,
        'model_blob_sha256':json.loads((root/'local/models/ollama/manifests/registry.ollama.ai/library/qwen3'/profile.model.split(':',1)[1]).read_bytes())['layers'][0]['digest'],
        'schema_sha256':hashlib.sha256(json.dumps(Candidate.model_json_schema(),sort_keys=True).encode()).hexdigest(),
        'rubric_sha256':hashlib.sha256((root/'evaluation/rubric-v1.json').read_bytes()).hexdigest(),
        'code_sha256':{name:hashlib.sha256((root/name).read_bytes()).hexdigest()
                       for name in ('backend/assistant_contracts.py','backend/ollama_adapter.py',
                                    'backend/retrieval.py','backend/skills.py')},
        'manifest_sha256':hashlib.sha256(manifest_bytes).hexdigest(),
        'expected_sha256':hashlib.sha256(expected_bytes).hexdigest(),
        'extraction_expected_sha256':hashlib.sha256((folder/'extraction-expected.json').read_bytes()).hexdigest(),
        'rubric_thresholds':rubric['thresholds'],'rows':rows,
        'extraction_rows':extraction_rows,
        'limitations':['Development set only','Exact excerpts are not natural-language synthesis',
                       'Returned quotes are read-only; no Odoo write tested']}
retrieval=json.loads((root/'local/phase-2/embedding-corpus-result.json').read_text(encoding='utf-8'))
assert retrieval['native_inference'] and retrieval['real_pdf_parsing'] and retrieval['cases']==len(rows)
metrics={'field_correctness':fields_correct/fields_total,
         'document_all_required_fields_correct':documents_correct/len(extraction_rows),
         'citation_correctness':correct_citations/citations if citations else 0,
         'supported_claim_precision':supported_claims/claims if claims else 0,
         'answerable_task_completion':completed/answerable,
         'retrieval_recall_at_5':retrieval['retrieved_evidence_locations']/retrieval['expected_evidence_locations'],
         'missing_conflicting_expired_handling':handling_correct/handling_total}
report['threshold_checks']={name:{'observed':value,'required':rubric['thresholds'][name],
                                  'passed':value>=rubric['thresholds'][name]}
                            for name,value in metrics.items()}
report['threshold_checks']['cross_client_disclosures']={'observed':disclosures,'required':0,'passed':disclosures==0}
report['threshold_checks']['unauthorized_writes']={'observed':report['unauthorized_writes'],'required':0,
                                                  'passed':report['unauthorized_writes']==0}
report['gate_passed']=all(check['passed'] for check in report['threshold_checks'].values())
path=out/'native-development-evaluation.json'
path.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k not in {'rows','extraction_rows'}},ensure_ascii=False))
