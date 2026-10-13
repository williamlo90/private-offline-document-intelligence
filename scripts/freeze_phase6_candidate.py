"""Freeze the native quality candidate only after all three declared splits pass."""
import hashlib
import json
from pathlib import Path
import sys

from backend.assistant_contracts import Candidate
from backend.ollama_adapter import PROMPT_SHA256

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'local/phase-6'
SPLITS=('development','regression-v1','regression-v2','regression-v3','regression-v4','regression-v5','heldout-v6')


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        while chunk:=stream.read(1024*1024):h.update(chunk)
    return h.hexdigest()


def main(run='final-8'):
    output=OUT/'candidate-freeze.json'
    if output.exists():raise RuntimeError('Candidate freeze already exists; refusing overwrite')
    reports={}
    for split in SPLITS:
        path=OUT/run/f'{split}-native.json'
        body=json.loads(path.read_text(encoding='utf-8'))
        if not body['gate_passed'] or body['errors'] or body['split']!=split:
            raise RuntimeError(f'{split} did not pass native quality gate')
        if body['prompt_sha256']!=PROMPT_SHA256 or body['rubric_sha256']!=sha(ROOT/'evaluation/rubric-v1.json'):
            raise RuntimeError(f'{split} prompt/rubric drift')
        if body['schema_sha256']!=hashlib.sha256(json.dumps(Candidate.model_json_schema(),sort_keys=True).encode()).hexdigest():
            raise RuntimeError(f'{split} response schema drift')
        for name,digest in body['code_sha256'].items():
            if sha(ROOT/name)!=digest:raise RuntimeError(f'{split} code drift: {name}')
        for name,digest in body['label_sha256'].items():
            folder={'development':'development','regression-v1':'heldout-v1','regression-v2':'heldout-v2','regression-v3':'heldout-v3','regression-v4':'heldout-v4','regression-v5':'heldout-v5','heldout-v6':'heldout-v6'}[split]
            if sha(ROOT/'evaluation'/folder/name)!=digest:raise RuntimeError(f'{split} label drift: {name}')
        for name,digest in body['source_sha256'].items():
            folder={'development':'development','regression-v1':'heldout-v1','regression-v2':'heldout-v2','regression-v3':'heldout-v3','regression-v4':'heldout-v4','regression-v5':'heldout-v5','heldout-v6':'heldout-v6'}[split]
            if sha(ROOT/'evaluation'/folder/name)!=digest:raise RuntimeError(f'{split} source drift: {name}')
        if body['latency_seconds']['assistant']['p95']>90 or body['latency_seconds']['search']['p95']>2:
            raise RuntimeError(f'{split} native latency SLO miss')
        reports[split]={'path':path.relative_to(ROOT).as_posix(),'sha256':sha(path),
                        'cases':body['case_count'],'extraction_documents':body['extraction_document_count'],
                        'counts':body['counts'],'latency_seconds':body['latency_seconds']}
    supervisor=OUT/run/'supervisor.json'
    resource=json.loads(supervisor.read_text(encoding='utf-8'))
    if resource['status']!='passed' or resource['minimum_linux_free_ram_gib']<1 or resource['sampled_peak_process_tree_rss_gib']>5.5:
        raise RuntimeError('Resource supervisor did not meet budget')
    app=ROOT/'local/offline-bundles/application-v6/manifest.json'
    assets=ROOT/'local/offline-bundles/native-assets-v5/manifest.json'
    if not app.is_file() or not assets.is_file():raise RuntimeError('App/asset bundle manifests missing')
    app_manifest=json.loads(app.read_text(encoding='utf-8'))
    app_archive=ROOT/'local/offline-bundles/application-v6/application.zip'
    if sha(app_archive)!=next(a['sha256'] for a in app_manifest['artifacts'] if a['id']=='application'):
        raise RuntimeError('Application bundle checksum mismatch')
    lock=ROOT/'config/ollama-runtime-lock.json'
    model=json.loads(lock.read_text(encoding='utf-8'))
    if model['prompt_sha256']!=PROMPT_SHA256:
        raise RuntimeError('Model lock prompt drift')
    freeze={'status':'native-quality-candidate-frozen','as_of':'2026-10-12','run':run,
            'rubric_sha256':sha(ROOT/'evaluation/rubric-v1.json'),
            'reports':reports,'supervisor':{'path':supervisor.relative_to(ROOT).as_posix(),
                                             'sha256':sha(supervisor),'resource':resource},
            'application_bundle':{'path':app.relative_to(ROOT).as_posix(),'manifest_sha256':sha(app),
                                  'archive_sha256':sha(app_archive)},
            'dependency_assets':{'path':assets.relative_to(ROOT).as_posix(),'manifest_sha256':sha(assets),
                                 'note':'Phase 5 model/runtime/language assets; app archive replaced by application-v6'},
            'model_lock_sha256':sha(lock),'model':model['model'],
            'phase7_required':['Persistent PostgreSQL/pgvector migrations, RLS, concurrency and restore',
                               'Connected Odoo #2 two-company approval/write/read-back and unknown-outcome recovery',
                               'Minimum full stack vertical slice and blocked-egress cold start',
                               'Service restart/reboot, disk-full/OOM, backup/restore and rollback',
                               'Repeat quality/ACL and normal/peak/soak SLO on final stack; check alerts and cleanup'],
            'limits':['Synthetic single-operator native lab, not customer/production outcome',
                      'Memory repository, not database durability or real Odoo',
                      'Search latency is in-memory keyword, not final persistent backend',
                      'Phase 7 must assemble/test full release bundle with application-v6 and dependency assets']}
    output.write_text(json.dumps(freeze,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({'status':freeze['status'],'splits':list(reports),'application_archive_sha256':sha(app_archive)}))


if __name__=='__main__':main(sys.argv[1] if len(sys.argv)>1 else 'final-8')
