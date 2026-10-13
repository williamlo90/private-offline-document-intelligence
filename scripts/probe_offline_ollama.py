"""Run one pinned native Ollama inference inside a loopback-only Linux namespace."""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import Request,ProxyHandler,build_opener

import psutil

root=Path(__file__).resolve().parents[1]
if sorted(name for _,name in socket.if_nameindex())!=['lo']:
    raise RuntimeError('Run only inside a loopback-only network namespace')
lock=json.loads((root/'config/ollama-runtime-lock.json').read_text())
linux_lock=json.loads((root/'config/ollama-linux-runtime-lock.json').read_text())
archive=root/'local/runtime/ollama-linux-amd64-v0.40.3.tar.zst'
digest=hashlib.sha256()
with archive.open('rb') as stream:
    while chunk:=stream.read(1024*1024):digest.update(chunk)
if digest.hexdigest()!=linux_lock['sha256']:raise RuntimeError('Linux Ollama archive checksum mismatch')
manifest=root/'local/models/ollama/manifests/registry.ollama.ai/library/qwen3/4b-instruct-2507-q4_K_M'
if hashlib.sha256(manifest.read_bytes()).hexdigest()!=lock['model']['manifest_sha256']:
    raise RuntimeError('Model manifest checksum mismatch')
binary=Path('/home/william/project07-lab-runtime/ollama/bin/ollama')
if not binary.is_file():raise RuntimeError('Project lab Linux Ollama runtime absent')
available=psutil.virtual_memory().available
gpu=subprocess.check_output(['/usr/lib/wsl/lib/nvidia-smi','--query-gpu=memory.free',
                             '--format=csv,noheader,nounits'],text=True).strip().splitlines()[0]
if available<3*1024**3 or int(gpu)<3500:raise RuntimeError('Insufficient free RAM or GPU memory')
with socket.socket() as reservation:
    reservation.bind(('127.0.0.1',0));port=reservation.getsockname()[1]
url=f'http://127.0.0.1:{port}'
env={**os.environ,'OLLAMA_HOST':f'127.0.0.1:{port}','OLLAMA_MODELS':str(root/'local/models/ollama'),
     'OLLAMA_NO_CLOUD':'1','OLLAMA_MAX_LOADED_MODELS':'1','OLLAMA_NUM_PARALLEL':'1','OLLAMA_KEEP_ALIVE':'0'}
server=subprocess.Popen([str(binary),'serve'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
opener=build_opener(ProxyHandler({}))
try:
    for _ in range(100):
        if server.poll() is not None:raise RuntimeError('Ollama startup failed: '+server.stderr.read(500).decode(errors='replace'))
        try:
            with opener.open(url+'/api/version',timeout=1) as response:version=json.load(response)['version'];break
        except (URLError,TimeoutError):time.sleep(.1)
    else:raise RuntimeError('Ollama startup timeout')
    if version!=linux_lock['version']:raise RuntimeError('Ollama version drift')
    request=Request(url+'/api/generate',method='POST',headers={'Content-Type':'application/json'},
                    data=json.dumps({'model':lock['model']['name'],'prompt':'Reply with one short word for readiness.',
                                     'stream':False,'think':False,'keep_alive':0,
                                     'options':{'temperature':0,'num_ctx':2048,'num_predict':24}}).encode())
    started=time.monotonic()
    with opener.open(request,timeout=150) as response:result=json.load(response)
    if not result.get('done') or not result.get('response','').strip():
        raise RuntimeError('Local model did not complete inference')
    report={'status':'passed','boundary':'Linux user+network namespace, loopback only',
            'runtime_version':version,'model':lock['model']['name'],'native_inference':True,
            'response_text':result['response'].strip()[:200],
            'eval_count':result.get('eval_count'),'load_duration_ns':result.get('load_duration'),
            'wall_seconds':round(time.monotonic()-started,3),
            'free_ram_before_gib':round(available/1024**3,2),'gpu_free_before_mib':int(gpu),
            'ollama_no_cloud':True,'hosted_fallback_used':False,
            'scope':'One native model smoke; Phase 3 rubric remains the quality evidence; no connected stack acceptance'}
    (root/'local/phase-5/offline-ollama-smoke.json').write_text(json.dumps(report,indent=2)+'\n')
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
