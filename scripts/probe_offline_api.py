"""Cold-start native memory API inside an already isolated Linux network namespace."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, ProxyHandler, build_opener


root=Path(__file__).resolve().parents[1]
if sorted(name for _,name in socket.if_nameindex())!=['lo']:
    raise RuntimeError('Run only inside a loopback-only network namespace')
config=root/'local/lab-identities.json'
identity=json.loads(config.read_text(encoding='utf-8'))
token=next(item['token'] for item in identity['actors'] if item['tenant']=='atlas' and item['role']=='technician')
with socket.socket() as reservation:
    reservation.bind(('127.0.0.1',0));port=reservation.getsockname()[1]
env={**os.environ,'PRIVATE_LAB_CONFIG':str(config),'PYTHONPATH':str(root)}
process=subprocess.Popen([sys.executable,'-m','uvicorn','backend.main:load_app','--factory',
                          '--host','127.0.0.1','--port',str(port),'--no-access-log'],
                         cwd=root,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
opener=build_opener(ProxyHandler({}))
base=f'http://127.0.0.1:{port}'
try:
    for _ in range(50):
        if process.poll() is not None:raise RuntimeError('API startup failed')
        try:
            with opener.open(base+'/health',timeout=1) as response:
                health=json.load(response);break
        except (URLError,TimeoutError):time.sleep(.1)
    else:raise RuntimeError('API startup timeout')
    request=Request(base+'/documents',headers={'Authorization':'Bearer '+token})
    with opener.open(request,timeout=5) as response:documents=json.load(response)
    request=Request(base+'/skills/answer_client_question',data=json.dumps({'question':'What is the response target?'}).encode(),
                    headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    try:
        with opener.open(request,timeout=5) as response:answer={'http':response.status,'body':json.load(response)}
    except HTTPError as error:answer={'http':error.code,'body':json.load(error)}
    result={'status':'passed','boundary':'isolated Linux namespace, loopback only',
            'health':health,'authorized_documents':len(documents),'assistant_http':answer['http'],
            'assistant_status':answer['body'].get('error',answer['body'].get('status')),
            'hosted_fallback_used':False,
            'scope':'Cold start of memory API without local Ollama; full assistant/model offline cold start remains pending'}
    if health['status']!='ok' or not documents or answer['http']!=503:raise RuntimeError('Unexpected native API behavior')
    (root/'local/phase-5/offline-api-smoke.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
finally:
    process.terminate()
    try:process.wait(timeout=5)
    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
