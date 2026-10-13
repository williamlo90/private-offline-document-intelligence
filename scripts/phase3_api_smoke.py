"""Native model through the authenticated FastAPI skill, on synthetic PDF text."""
import hashlib
import json
from pathlib import Path
import sys

from fastapi.testclient import TestClient

from backend.api import create_app
from backend.domain import Actor
from backend.ollama_adapter import OllamaGenerator, OllamaProfile
from backend.pdf_parser import parse_pdf

root=Path(__file__).resolve().parents[1]
profile=OllamaProfile.model_validate_json(Path(sys.argv[1]).read_bytes())
output=Path(sys.argv[2])
atlas_token='atlas-native-smoke-token-123456789'
birch_token='birch-native-smoke-token-123456789'
atlas=Actor('atlas-smoke','atlas','technician')
birch=Actor('birch-smoke','birch','technician')
app=create_app({atlas_token:atlas,birch_token:birch})
app.state.skills.assistant.generator=OllamaGenerator(profile)
manifest=json.loads((root/'evaluation/development/manifest.json').read_text(encoding='utf-8'))
source=next(item for item in manifest['documents'] if item['id']=='atlas-sla-v1')
data=(root/'evaluation/development'/source['file']).read_bytes()
assert hashlib.sha256(data).hexdigest()==source['sha256']
parsed=parse_pdf(data)
app.state.service.ingest(atlas,source['id'],source['id'],'\n\n'.join(p.text for p in parsed.pages),
                         pages=parsed.pages,source_hash=parsed.sha256,effective=source['effective'],
                         expires=source['expires'],family=source['family'])
client=TestClient(app)
question={'question':'What is the critical initial response target?'}
authorized=client.post('/skills/answer_client_question',json=question,
                       headers={'Authorization':'Bearer '+atlas_token})
anonymous=client.post('/skills/answer_client_question',json=question)
other=client.post('/skills/answer_client_question',json=question,
                  headers={'Authorization':'Bearer '+birch_token})
body=authorized.json()
excerpts=body.get('excerpts',[])
exact=bool(excerpts) and all(
    next(p for p in parsed.pages if p.number==entry['evidence']['page']).text[
        entry['evidence']['start']:entry['evidence']['end']]==entry['value']
    for entry in excerpts)
report={'native_api':True,'authorized_http':authorized.status_code,
        'authorized_status':body.get('status'),'exact_citations':exact,
        'contains_60_minutes':any('60 minutes' in entry['value'] for entry in excerpts),
        'anonymous_http':anonymous.status_code,'other_tenant_http':other.status_code,
        'other_tenant_disclosure':'60 minutes' in other.text,
        'unauthorized_writes':len(app.state.service.repo.proposals('atlas')),
        'model':profile.model,'model_digest':profile.digest}
report['gate_passed']=(report['authorized_http']==200 and report['authorized_status']=='sourced_excerpts'
                       and exact and report['contains_60_minutes'] and report['anonymous_http']==401
                       and report['other_tenant_http'] in (200,403,404)
                       and not report['other_tenant_disclosure'] and report['unauthorized_writes']==0)
output.write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
