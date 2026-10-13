"""Targeted native regression probe after a held-out family joins development."""
import hashlib
import json
from pathlib import Path
import sys

from backend.assistant_contracts import Extraction, Question
from backend.domain import Actor, MemoryRepository, Service
from backend.ollama_adapter import OllamaGenerator, OllamaProfile
from backend.pdf_parser import parse_pdf
from backend.skills import BusinessSkills

root=Path(__file__).resolve().parents[1]
folder=root/'evaluation/heldout-v1'
manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
service=Service(MemoryRepository())
for item in manifest['documents']:
    data=(folder/item['file']).read_bytes()
    assert hashlib.sha256(data).hexdigest()==item['sha256']
    parsed=parse_pdf(data,language=item.get('language','eng'))
    service.ingest(Actor('probe',item['tenant'],'technician'),item['id'],item['id'],
                   '\n\n'.join(p.text for p in parsed.pages),pages=parsed.pages,source_hash=parsed.sha256,
                   effective=item['effective'],expires=item['expires'],family=item['family'])
profile=OllamaProfile.model_validate_json((root/'config/ollama-profile.json').read_bytes())
skills=BusinessSkills(service,root/'local/offline-bundle',OllamaGenerator(profile))
birch=Actor('probe','birch','technician')
answer=skills.answer_client_question(birch,Question(question='What does the Birch firewall policy review cover and exclude?'))
document=service.read_document(birch,'birch-power-sop')
extraction=skills.extract_service_terms(birch,Extraction(document_id=document.id,version=document.version))
report={'answer':answer.model_dump(mode='json'),'extraction':extraction.model_dump(mode='json')}
path=Path(sys.argv[1]);assert not path.exists()
path.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print(json.dumps({'answer_status':answer.status,'answer_values':[e.value for e in answer.excerpts],
                  'extraction':[(e.kind,e.value) for e in extraction.excerpts]},ensure_ascii=False),flush=True)
