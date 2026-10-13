"""Actual sourced answer through FastAPI/skills and pinned Ollama in an isolated namespace."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import ProxyHandler,build_opener

import psutil

root=Path(__file__).resolve().parents[1]
if sorted(name for _,name in socket.if_nameindex())!=['lo']:
    raise RuntimeError('Run only inside a loopback-only network namespace')
if psutil.virtual_memory().available<3*1024**3:raise RuntimeError('Insufficient preflight memory')
profile=json.loads((root/'config/ollama-profile.json').read_text())
port=profile['port'];url=f'http://127.0.0.1:{port}/api/version'
binary='/home/william/project07-lab-runtime/ollama/bin/ollama'
env={**os.environ,'OLLAMA_HOST':f'127.0.0.1:{port}','OLLAMA_MODELS':str(root/'local/models/ollama'),
     'OLLAMA_NO_CLOUD':'1','OLLAMA_MAX_LOADED_MODELS':'1','OLLAMA_NUM_PARALLEL':'1','OLLAMA_KEEP_ALIVE':'0'}
server=subprocess.Popen([binary,'serve'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
try:
    opener=build_opener(ProxyHandler({}))
    for _ in range(100):
        if server.poll() is not None:raise RuntimeError('Ollama startup failed')
        try:
            with opener.open(url,timeout=1) as response:version=json.load(response)['version'];break
        except (URLError,TimeoutError):time.sleep(.1)
    else:raise RuntimeError('Ollama startup timeout')
    if version!='0.40.3':raise RuntimeError('Ollama runtime version drift')
    output=root/'local/phase-5/offline-ai-api-smoke.json'
    run=subprocess.run([sys.executable,'scripts/phase3_api_smoke.py',str(root/'config/ollama-profile.json'),str(output)],
                       cwd=root,env={**env,'PYTHONPATH':str(root)},capture_output=True,text=True,timeout=180)
    if run.returncode:raise RuntimeError('Offline assistant smoke failed: '+run.stderr[-1200:])
    report=json.loads(output.read_text())
    if not report['gate_passed']:raise RuntimeError('Offline assistant smoke did not meet source assertions')
    report.update(offline_boundary='Linux user+network namespace, loopback only',ollama_version=version,
                  ollama_no_cloud=True,hosted_fallback_used=False,
                  scope='One sourced native assistant task with exact citations and tenant checks; not full stack acceptance')
    output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
finally:
    children=psutil.Process(server.pid).children(recursive=True) if server.poll() is None else []
    server.terminate()
    try:server.wait(timeout=10)
    except subprocess.TimeoutExpired:server.kill();server.wait(timeout=10)
    for child in children:
        try:child.terminate()
        except psutil.NoSuchProcess:pass
    _,alive=psutil.wait_procs(children,timeout=5)
    for child in alive:
        try:child.kill()
        except psutil.NoSuchProcess:pass
