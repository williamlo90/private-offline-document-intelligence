"""Supervised native embedding evaluation on frozen synthetic development PDFs."""
from datetime import date
import hashlib
import json
from pathlib import Path
import sys
import time

import psutil
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.domain import Actor, MemoryRepository, Service
from backend.embeddings import LocalEmbeddings
from backend.native_retrieval import NativeVectorIndex
from backend.pdf_parser import parse_pdf

root=Path(__file__).resolve().parents[1]
profile=json.loads((root/'config/embedding-profile.json').read_text(encoding='utf-8'))
folder=root/'evaluation/development'
manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
expected=json.loads((folder/'expected.json').read_text(encoding='utf-8'))
service=Service(MemoryRepository())
for item in manifest['documents']:
    data=(folder/item['file']).read_bytes()
    assert hashlib.sha256(data).hexdigest()==item['sha256']
    parsed=parse_pdf(data)
    service.ingest(Actor('evaluator',item['tenant'],'technician'),item['id'],item['id'],
                   '\n\n'.join(p.text for p in parsed.pages),pages=parsed.pages,source_hash=parsed.sha256,
                   effective=item['effective'],expires=item['expires'],family=item['family'])
encoder=LocalEmbeddings(root/'local/models/multilingual-minilm',profile)
index=NativeVectorIndex(encoder,profile['revision'])
rows=[];matched=0;total=0;quotes=0;spans=0;returned=0
started=time.monotonic()
for case in expected['cases']:
    actor=Actor('evaluator',case['tenant'],'technician')
    results=index.search(service,actor,case['question'],date.fromisoformat(expected['as_of']))
    references={(identifier,page) for identifier,page,_ in case['evidence']}
    observed={(r['document_id'],r['page']) for r in results}
    matched+=len(references&observed);total+=len(references)
    norm=lambda value:' '.join(value.split())
    quote_matches=sum(any(r['document_id']==identifier and r['page']==page and norm(quote) in norm(r['quote'])
                          for r in results) for identifier,page,quote in case['evidence'])
    quotes+=quote_matches
    for result in results:
        document=service.read_version(actor,result['document_id'],result['version'])
        page=next(p for p in document.pages if p.number==result['page'])
        assert document.tenant==case['tenant']
        assert result['model_revision']==profile['revision']
        spans+=int(document.digest==result['sha256'] and page.text[result['start']:result['end']]==result['quote'])
    returned+=len(results)
    rows.append({'id':case['id'],'expected_locations':len(references),'retrieved_locations':len(references&observed),
                 'expected_quotes_found':quote_matches,'result_count':len(results),
                 'top_results':[{'document_id':r['document_id'],'page':r['page'],'status':r['status'],
                                 'score':round(r['score'],4)} for r in results]})
token='native-corpus-http-check-0123456789'
app=create_app({token:Actor('evaluator','atlas','technician')},repository=service.repo)
app.state.semantic=index
response=TestClient(app).get('/semantic-search',params={'q':'critical response','as_of':expected['as_of']},
                             headers={'Authorization':'Bearer '+token})
assert response.status_code==200,response.text
assert response.json() and all(service.repo.document('atlas',r['document_id']) is not None for r in response.json())
report={'status':'passed' if spans==returned else 'failed-span-integrity',
        'native_inference':True,'model_revision':profile['revision'],'cases':len(rows),
        'retrieved_evidence_locations':matched,'expected_evidence_locations':total,
        'expected_quote_coverage':{'matched':quotes,'total':total},
        'returned_span_integrity':{'valid':spans,'total':returned},
        'seconds':round(time.monotonic()-started,3),
        'worker_rss_after_evaluation_gib':round(psutil.Process().memory_info().rss/1024**3,3),
        'native_http_status':response.status_code,'native_http_result_count':len(response.json()),
        'split':'development','real_pdf_parsing':True,'rows':rows,
        'scope':'Native vector retrieval development-set location/quote coverage and exact source spans; not answer quality or held-out evidence'}
Path(sys.argv[1]).write_text(json.dumps(report,indent=2),encoding='utf-8')
