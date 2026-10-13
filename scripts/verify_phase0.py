"""Check source/label consistency and capture the read-only reuse snapshot."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def main():
    scope = read(ROOT / 'config/scope-v1.json')
    rubric = read(ROOT / 'evaluation/rubric-v1.json')
    deps = read(ROOT / 'config/dependency-map.json')
    corpus = read(ROOT / 'evaluation/development/manifest.json')
    cases = read(ROOT / 'evaluation/development/expected.json')['cases']
    docs = {d['id']: d for d in corpus['documents']}
    assert len(docs) == len(corpus['documents'])
    assert len({c['id'] for c in cases}) == len(cases)
    assert set(d['tenant'] for d in docs.values()) == set(scope['tenants'])
    assert rubric['frozen_before_model_selection']
    for d in docs.values():
        assert hashlib.sha256((ROOT / 'evaluation/development' / d['file']).read_bytes()).hexdigest() == d['sha256']
    for case in cases:
        for identifier, page, quote in case['evidence']:
            doc = docs[identifier]
            assert doc['tenant'] == case['tenant']
            assert quote in doc['pages'][page - 1]['text']
    assert {'missing', 'conflicting', 'expired'} <= {c['status'] for c in cases}
    snapshots = []
    for source in deps['reuse']:
        path = (ROOT / source['source']).resolve()
        revision = subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
        status = subprocess.check_output(['git', '-C', str(path), 'status', '--short'], text=True)
        selected = {p: hashlib.sha256((path / p).read_bytes()).hexdigest() for p in source['files']}
        snapshots.append({'source': source['source'], 'expected_revision': source['revision'], 'observed_revision': revision, 'revision_matches': revision == source['revision'], 'status': status.splitlines(), 'selected_file_sha256': selected})
        assert revision == source['revision'], 'Upstream changed; review before reusing contract'
    out = ROOT / 'local/phase-0'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'reuse-snapshot.json').write_text(json.dumps(snapshots, indent=2), encoding='utf-8')
    result = {'phase': 0, 'checks': 'passed', 'documents': len(docs), 'source_pages': sum(len(d['pages']) for d in docs.values()), 'development_cases': len(cases), 'scope': 'Planning gate and development fixture integrity only; no application/model/integration claim', 'visual_review': '11 rendered source pages inspected; no clipping observed', 'pending_later': ['scan variants', 'independent held-out corpus', 'model/runtime provisioning and native acceptance', 'Odoo contract extension', 'isolated offline boundary']}
    (out / 'verification.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))

if __name__ == '__main__':
    main()
