"""Measure baseline retrieval on declared development fixtures, without generation."""
from datetime import date
import hashlib
import json
from pathlib import Path
import time

from backend.domain import Actor, MemoryRepository, Service
from backend.pdf_parser import parse_pdf

root=Path(__file__).resolve().parents[1]
manifest_path=root/'evaluation/development/manifest.json'
manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
expected=json.loads((manifest_path.parent/'expected.json').read_text(encoding='utf-8'))
service=Service(MemoryRepository())
for document in manifest['documents']:
    data=(manifest_path.parent/document['file']).read_bytes()
    assert hashlib.sha256(data).hexdigest()==document['sha256']
    parsed=parse_pdf(data)
    service.ingest(Actor('evaluator',document['tenant'],'technician'),document['id'],document['id'],
                   '\n\n'.join(p.text for p in parsed.pages),pages=parsed.pages,source_hash=parsed.sha256,
                   effective=document['effective'],expires=document['expires'],family=document['family'])
rows=[];found=0;total=0;expected_quotes_found=0;quote_total=0;span_valid=0;result_total=0;labeled_relevant_results=0
for case in expected['cases']:
    started=time.monotonic()
    results=service.search(Actor('evaluator',case['tenant'],'technician'),case['question'],date.fromisoformat(expected['as_of']))
    references={(identifier,page) for identifier,page,quote in case['evidence']}
    observed={(r['document_id'],r['page']) for r in results}
    matched=len(references&observed);found+=matched;total+=len(references)
    normalize=lambda text:' '.join(text.split())
    quotes_matched=sum(any(r['document_id']==identifier and r['page']==page and normalize(quote) in normalize(r['quote'])
                          for r in results) for identifier,page,quote in case['evidence'])
    expected_quotes_found+=quotes_matched;quote_total+=len(case['evidence'])
    for r in results:
        source=service.read_version(Actor('verifier',case['tenant'],'technician'),r['document_id'],r['version'])
        source_page=next(p for p in source.pages if p.number==r['page'])
        span_valid+=int(source.digest==r['sha256'] and source_page.text[r['start']:r['end']]==r['quote'])
        labeled_relevant_results+=int((r['document_id'],r['page']) in references)
    result_total+=len(results)
    rows.append({'id':case['id'],'expected_status':case['status'],'reference_locations':len(references),'retrieved_locations':matched,
                 'result_count':len(results),'expected_quotes_found':quotes_matched,'no_reference_case_with_hits':not references and bool(results),
                 'results':[{'id':r['document_id'],'page':r['page'],'status':r['status']} for r in results],
                 'seconds':round(time.monotonic()-started,6)})
report={'split':'development','method':'keyword-v1','real_pdf_parsing':True,'cases':len(rows),'retrieval_recall_at_5':found/total,
        'retrieved_evidence_locations':found,'expected_evidence_locations':total,
        'expected_quote_coverage':{'matched':expected_quotes_found,'total':quote_total},
        'returned_span_integrity':{'valid':span_valid,'total':result_total},
        'reference_labeled_result_precision':{'labeled_relevant':labeled_relevant_results,'returned':result_total},
        'no_reference_cases_with_hits':sum(r['no_reference_case_with_hits'] for r in rows),
        'manifest_sha256':hashlib.sha256(manifest_path.read_bytes()).hexdigest(),'rows':rows,
        'scope':'Location recall, expected-quote substring coverage and exact source-span integrity. Reference precision uses a limited gold set, not exhaustive relevance judgments. Generated answer entailment and abstention are not measured.',
        'limitations':['Small development set, not held-out','Keyword results may be irrelevant for missing/injection questions','No AI quality pass or semantic embedding claim']}
out=root/'local/phase-2/keyword-baseline.json';out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='rows'}))
