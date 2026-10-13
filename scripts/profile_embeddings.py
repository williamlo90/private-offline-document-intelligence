"""Supervise only our embedding subprocess; stop on memory pressure or timeout."""
import json
from pathlib import Path
import subprocess
import sys
import time
import psutil
from backend.resources import available_memory_bytes

root=Path(__file__).resolve().parents[1]
mode=sys.argv[1] if len(sys.argv)>1 else 'smoke'
if mode not in {'smoke','corpus'}:
    raise SystemExit('usage: python -m scripts.profile_embeddings [smoke|corpus]')
profile=json.loads((root/'config/embedding-profile.json').read_text(encoding='utf-8-sig'))
out=root/'local/phase-2';out.mkdir(parents=True,exist_ok=True)
report_path=out/('embedding-profile-result.json' if mode=='smoke' else 'embedding-corpus-profile-result.json')
free=available_memory_bytes()
report={'available_before_gib':round(free/1024**3,3),'required_gib':profile['minimum_available_ram_gib'],
        'native_inference':False,'monitor_interval_seconds':.05,'mode':mode,
        'scope':'Sampled owned-process-tree RSS stop policy, not a hard OS memory allocation cap'}
if free<profile['minimum_available_ram_gib']*1024**3:
    report['status']='pending-resource-budget'
else:
    result_path=out/('embedding-smoke-result.json' if mode=='smoke' else 'embedding-corpus-result.json')
    if result_path.exists():result_path.unlink()
    with (out/'embedding-worker.log').open('w',encoding='utf-8') as log:
        worker='scripts.embedding_smoke_worker' if mode=='smoke' else 'scripts.evaluate_native_retrieval'
        process=subprocess.Popen([sys.executable,'-m',worker,str(result_path)],cwd=root,
                                 stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        owned=psutil.Process(process.pid);peak=0;minimum=free;reason=None;started=time.monotonic()
        try:
            while process.poll() is None:
                # Windows venv python.exe can be a small launcher with the actual
                # interpreter as its child. Account for every owned descendant.
                try:
                    processes=[owned,*owned.children(recursive=True)]
                    rss=sum(p.memory_info().rss for p in processes if p.is_running())
                    peak=max(peak,rss)
                except psutil.NoSuchProcess:
                    pass
                minimum=min(minimum,available_memory_bytes())
                if peak>profile['provisional_process_budget_gib']*1024**3:reason='process_memory_budget'
                elif minimum<profile['minimum_runtime_available_ram_gib']*1024**3:reason='host_memory_reserve'
                elif time.monotonic()-started>120:reason='timeout'
                if reason:break
                time.sleep(.05)
        finally:
            if process.poll() is None:
                for child in owned.children(recursive=True):
                    try:child.kill()
                    except psutil.NoSuchProcess:pass
                process.kill()
            process.wait(timeout=10)
        report.update({'peak_rss_gib':round(peak/1024**3,3),'minimum_available_gib':round(minimum/1024**3,3),
                       'exit_code':process.returncode,'seconds':round(time.monotonic()-started,3)})
        if reason:report['status']='stopped-'+reason
        elif process.returncode or not result_path.exists():report['status']='failed-see-local-worker-log'
        else:
            report.update(json.loads(result_path.read_text(encoding='utf-8')))
            report['memory_measurement']='Sampled at 50ms; spikes between samples may be missed'
report_path.write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
