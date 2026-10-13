"""Own one isolated loopback Ollama daemon and supervise one native lab run."""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx
import psutil

from backend.assistant_contracts import Candidate
from backend.ollama_adapter import OllamaProfile, PROMPT_SHA256
from backend.resources import available_memory_bytes

def free_vram_mib():
    run=subprocess.run(['nvidia-smi','--query-gpu=memory.free','--format=csv,noheader,nounits'],
                       capture_output=True,text=True,timeout=5,check=True)
    return int(run.stdout.strip().splitlines()[0])

root=Path(__file__).resolve().parents[1]
mode=sys.argv[1] if len(sys.argv)>1 else 'probe'
if mode not in {'probe','evaluate','api_smoke'}:
    raise SystemExit('usage: python -m scripts.run_phase3_lab [probe|evaluate|api_smoke]')
runtime=root/'local/runtime/ollama-v0.40.3/ollama.exe'
model_root=root/'local/models/ollama'
profile_path=root/'config/ollama-profile.json'
profile=OllamaProfile.model_validate_json(profile_path.read_bytes())
lock=json.loads((root/'config/ollama-runtime-lock.json').read_text(encoding='utf-8'))
if (lock['runtime']['version']!='0.40.3' or
    lock['runtime']['executable_sha256']!=hashlib.sha256(runtime.read_bytes()).hexdigest() or
    lock['model']['name']!=profile.model or lock['model']['manifest_sha256']!=profile.digest or
    lock['prompt_sha256']!=PROMPT_SHA256 or
    lock['candidate_schema_sha256']!=hashlib.sha256(json.dumps(Candidate.model_json_schema(),sort_keys=True).encode()).hexdigest() or
    lock['development_rubric_sha256']!=hashlib.sha256((root/'evaluation/rubric-v1.json').read_bytes()).hexdigest()):
    raise RuntimeError('phase3_runtime_lock_mismatch')
manifest_path=model_root/'manifests/registry.ollama.ai/library/qwen3'/profile.model.split(':',1)[1]
manifest_bytes=manifest_path.read_bytes()
if hashlib.sha256(manifest_bytes).hexdigest()!=profile.digest:
    raise RuntimeError('model_manifest_digest_mismatch')
manifest=json.loads(manifest_bytes)
if (manifest['layers'][0]['digest']!='sha256:'+lock['model']['gguf_sha256'] or
    manifest['layers'][0]['size']!=lock['model']['gguf_bytes']):
    raise RuntimeError('phase3_model_lock_mismatch')
for part in [manifest['config'],*manifest['layers']]:
    digest=part['digest'].removeprefix('sha256:')
    blob=model_root/'blobs'/('sha256-'+digest)
    if not blob.is_file() or blob.stat().st_size!=part['size']:
        raise RuntimeError('model_blob_missing_or_wrong_size')
    # Hash the large GGUF too; this happens before model loading.
    with blob.open('rb') as stream:
        hashed=hashlib.file_digest(stream,'sha256').hexdigest()
    if hashed!=digest:
        raise RuntimeError('model_blob_checksum_mismatch')
if available_memory_bytes()<profile.minimum_free_ram_gib*1024**3:
    raise RuntimeError('resource_budget_unavailable')
if free_vram_mib()<4608:
    raise RuntimeError('gpu_resource_budget_unavailable')
with socket.socket() as listener:
    listener.bind(('127.0.0.1',profile.port))  # Fail if another daemon owns the port.
out=root/'local/phase-3';out.mkdir(parents=True,exist_ok=True)
result_path=out/({'probe':'probe-worker.json','evaluate':'native-development-evaluation.json',
                 'api_smoke':'api-smoke.json'}[mode])
if result_path.exists():result_path.unlink()
env=os.environ.copy()
env.update({'OLLAMA_HOST':f'127.0.0.1:{profile.port}', 'OLLAMA_MODELS':str(model_root),
            'OLLAMA_NO_CLOUD':'1','OLLAMA_MAX_LOADED_MODELS':'1','OLLAMA_NUM_PARALLEL':'1',
            'OLLAMA_KEEP_ALIVE':'0'})
owned=[]
def track(process):
    try:
        for item in [psutil.Process(process.pid),*psutil.Process(process.pid).children(recursive=True)]:
            if not any(p.pid==item.pid and p.create_time()==item.create_time() for p in owned):
                owned.append(item)
    except psutil.NoSuchProcess:
        pass
def rss():
    total=0
    for process in owned:
        try:total+=process.memory_info().rss
        except (psutil.NoSuchProcess,psutil.AccessDenied):pass
    return total
daemon=None;worker=None;reason=None;started=time.monotonic();peak=0;minimum_ram=available_memory_bytes();minimum_vram=free_vram_mib()
last_gpu_check=started
try:
    with (out/'ollama-daemon.log').open('w',encoding='utf-8') as log, (out/(mode+'-worker.log')).open('w',encoding='utf-8') as worker_log:
        daemon=subprocess.Popen([str(runtime),'serve'],cwd=runtime.parent,env=env,
                                stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            track(daemon)
            if daemon.poll() is not None:raise RuntimeError('dedicated_ollama_exited')
            try:
                response=httpx.get(f'http://127.0.0.1:{profile.port}/api/tags',trust_env=False,timeout=1)
                if response.status_code==200:break
            except httpx.HTTPError:pass
            time.sleep(.2)
        else:raise RuntimeError('dedicated_ollama_start_timeout')
        command=([sys.executable,'-m','scripts.phase3_probe_worker',str(profile_path),str(result_path)]
                 if mode=='probe' else [sys.executable,'-m','scripts.evaluate_phase3',str(profile_path)]
                 if mode=='evaluate' else [sys.executable,'-m','scripts.phase3_api_smoke',str(profile_path),str(result_path)])
        worker=subprocess.Popen(command,cwd=root,env=env,stdout=worker_log,stderr=worker_log,
                                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        while worker.poll() is None:
            track(daemon);track(worker)
            peak=max(peak,rss())
            minimum_ram=min(minimum_ram,available_memory_bytes())
            if time.monotonic()-started>1800:reason='timeout'
            elif minimum_ram<profile.runtime_reserve_gib*1024**3:reason='host_memory_reserve'
            elif peak>2.5*1024**3:reason='owned_process_memory_budget'
            if time.monotonic()-last_gpu_check>1:
                minimum_vram=min(minimum_vram,free_vram_mib())
                last_gpu_check=time.monotonic()
                if minimum_vram<256:reason='gpu_memory_reserve'
            if reason:break
            time.sleep(.1)
        if worker.poll() is None:worker.kill()
        worker.wait(timeout=10)
finally:
    for process in reversed(owned):
        try:process.kill()
        except (psutil.NoSuchProcess,psutil.AccessDenied):pass
    if daemon is not None and daemon.poll() is None:
        daemon.kill();daemon.wait(timeout=10)
execution_ok=not reason and worker and worker.returncode==0 and result_path.exists()
quality_ok=(mode=='probe' or json.loads(result_path.read_text(encoding='utf-8')).get('gate_passed',False)) if execution_ok else False
report={'mode':mode,'status':'passed' if execution_ok and quality_ok else ('quality_failed' if execution_ok else reason or 'failed-see-local-worker-log'),
        'native_inference':bool(result_path.exists()),'runtime':'ollama-v0.40.3','model':profile.model,
        'model_digest':profile.digest,'sampled_peak_owned_rss_gib':round(peak/1024**3,3),
        'minimum_host_free_gib':round(minimum_ram/1024**3,3),
        'minimum_gpu_free_mib':minimum_vram,'seconds':round(time.monotonic()-started,3),
        'scope':'Dedicated loopback process tree; 100ms RAM samples, GPU snapshots; no hard OS allocation cap'}
(out/(mode+'-supervisor.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
