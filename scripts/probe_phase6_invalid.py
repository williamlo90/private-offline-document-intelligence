"""Inspect a rejected native selection on synthetic regression source only."""
import hashlib
import json
from pathlib import Path
import sys

from backend.assistant_contracts import Extraction
from backend.domain import Actor, DomainError, MemoryRepository, Service
from backend.ollama_adapter import OllamaGenerator, OllamaProfile
from backend.pdf_parser import parse_pdf
from backend.skills import BusinessSkills

root=Path(__file__).resolve().parents[1]
folder=root/'evaluation/heldout-v3'
item=next(x for x in json.loads((folder/'manifest.json').read_text())['documents'] if x['id']=='birch-guest-wifi')
data=(folder/item['file']).read_bytes();assert hashlib.sha256(data).hexdigest()==item['sha256']
parsed=parse_pdf(data,language=item['language'])
actor=Actor('probe','birch','technician')
service=Service(MemoryRepository())
document=service.ingest(actor,item['id'],item['id'],'\n\n'.join(p.text for p in parsed.pages),
                        pages=parsed.pages,source_hash=parsed.sha256,effective=item['effective'],
                        expires=item['expires'],family=item['family'])
profile=OllamaProfile.model_validate_json((root/'config/ollama-profile.json').read_bytes())
class Recording:
    def __init__(self):self.native=OllamaGenerator(profile);self.raw=None;self.payload=None
    def generate(self,task,payload,schema):
        self.payload=payload
        self.raw=self.native.generate(task,payload,schema)
        return self.raw
recording=Recording()
skills=BusinessSkills(service,root/'local/offline-bundle',recording)
try:
    result=skills.extract_service_terms(actor,Extraction(document_id=document.id,version=document.version))
    outcome={'status':result.status,'excerpts':[e.model_dump(mode='json') for e in result.excerpts]}
except DomainError as error:
    outcome={'error':error.code}
report={'source_pages':[p.text for p in document.pages], 'evidence':recording.payload['evidence'],
        'raw':recording.raw,'outcome':outcome}
path=Path(sys.argv[1]);assert not path.exists()
path.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print(json.dumps({'outcome':outcome,'selections':recording.raw.get('selections') if recording.raw else None},ensure_ascii=False),flush=True)
