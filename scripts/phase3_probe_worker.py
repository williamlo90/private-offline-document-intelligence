"""One native synthetic structured-output probe; run only under run_phase3_lab."""
import json
from pathlib import Path
import sys
import time

import httpx

from backend.assistant_contracts import Candidate
from backend.ollama_adapter import OllamaProfile, SYSTEM

profile=OllamaProfile.model_validate_json(Path(sys.argv[1]).read_bytes())
result_path=Path(sys.argv[2])
base=f'http://127.0.0.1:{profile.port}'
started=time.monotonic()
quote='For critical incidents, the initial response target is 60 minutes.'
with httpx.Client(base_url=base,trust_env=False,follow_redirects=False,timeout=120) as client:
    tags=client.get('/api/tags').json()['models']
    assert any(m['name']==profile.model and m['digest']==profile.digest for m in tags)
    assert not client.get('/api/ps').json()['models']
    response=client.post('/api/generate',json={
        'model':profile.model,'system':SYSTEM,
        'prompt':json.dumps({'task':'answer_client_question','question':'What is the critical response target?',
                             'evidence':{'e0':{'document_id':'synthetic','version':1,'page':1,
                                              'start':0,'end':len(quote),'quote':quote}}}),
        'format':Candidate.model_json_schema(),'stream':False,'keep_alive':0,
        'options':{'temperature':0,'seed':0,'num_ctx':4096,'num_predict':384,'num_thread':4}})
    response.raise_for_status()
    body=response.json()
    result_path.with_name('probe-raw.json').write_text(json.dumps(body,indent=2),encoding='utf-8')
    assert body.get('done') is True and body.get('done_reason')=='stop'
    candidate=Candidate.model_validate(json.loads(body['response']))
    assert candidate.status=='supported'
    assert any(s.evidence_id=='e0' and '60 minutes' in s.quote and s.kind=='sla' for s in candidate.selections)
result_path.write_text(json.dumps({'status':'passed','native_inference':True,'candidate':candidate.model_dump(),
                                   'seconds':round(time.monotonic()-started,3)},indent=2),encoding='utf-8')
