"""Verify and freeze the revised Phase 7 portfolio evidence after lab shutdown."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / 'local/phase-7'
OUT = LOCAL / 'final-evidence-manifest.json'
IMAGE = 'sha256:97308d0926258c7ada1ae3cd09c8023f2c8a8f2068604c876ce8bc8e1a2b4966'
EVIDENCE = [
    'local/phase-7/database-restore-acceptance.json',
    'local/phase-7/database-rls-probe.json',
    'local/phase-7/odoo-connected-acceptance.json',
    'local/phase-7/browser-live.json',
    'local/phase-7/mcp-live.json',
    'local/phase-7/heldout-final.json',
    'local/phase-7/local-alert.json',
    'local/phase-7/final-smoke.json',
    'local/phase-7/final-ocr.json',
    'local/phase-7/final-load.json',
    'local/phase-7/final-resource-summary.json',
    'local/phase-7/final-network-audit.json',
    'local/phase-7/final-cold-start-limitation.json',
    'local/phase-7/final-tests.xml',
    'docs/PHASE-7-PORTFOLIO.md',
    'PHASES.md',
    'README.md',
]
CODE = [
    'backend/assistant_contracts.py', 'backend/ollama_adapter.py',
    'backend/api.py', 'backend/main.py', 'deploy/compose.offline.yaml',
    'scripts/phase7_load.py',
]


def digest(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def read(name: str):
    return json.loads((LOCAL / name).read_text(encoding='utf-8-sig'))


def main() -> None:
    if OUT.exists():
        raise RuntimeError('Refusing to overwrite final evidence manifest')
    smoke, ocr, load, resources, network = (read(name) for name in
        ('final-smoke.json', 'final-ocr.json', 'final-load.json',
         'final-resource-summary.json', 'final-network-audit.json'))
    quality, platform = read('heldout-final.json'), read('odoo-connected-acceptance.json')
    assert all(row['status'] == 'passed' for row in
               (smoke, ocr, load, resources, network, quality, platform))
    assert network['services']['api']['image_id'] == IMAGE
    assert smoke['offline_tested'] and smoke['cross_tenant_source_denied']
    assert smoke['odoo_readback_verified'] and smoke['replay_external_id_unchanged']
    assert ocr['native_ocr'] and ocr['cross_tenant_read_denied']
    assert quality['forbidden_disclosures'] == 0 and quality['errors'] == 0
    assert quality['metrics']['answerable_completion'] == [7, 7]
    assert quality['metrics']['uncertainty_handling'] == [6, 6]
    assert load['answer']['n'] == 7 and load['search']['n'] == 20
    assert load['errors'] == 0 and load['verified_completion']
    assert load['search']['p95'] <= 2 and load['answer']['p95'] <= 90
    assert load['queue_wait_seconds']['n'] == 7
    assert resources['samples'] >= 20 and resources['status'] == 'passed'
    assert network['internal'] and not network['host_ports_published']
    assert platform['readback_verified'] and not platform['replay_created_new_effect']
    suite = ET.parse(LOCAL / 'final-tests.xml').getroot().find('testsuite')
    assert suite is not None and int(suite.attrib['tests']) == 154
    assert int(suite.attrib['failures']) == int(suite.attrib['errors']) == 0
    active = subprocess.run(['docker', 'ps', '--filter',
                             'label=com.docker.compose.project=private-documents-phase7',
                             '--format', '{{.Names}}'], capture_output=True, text=True, check=True)
    assert not active.stdout.strip(), 'Project test services still running'
    image = subprocess.run(['docker', 'image', 'inspect', 'private-documents-api:phase7',
                            '--format', '{{.Id}}'], capture_output=True, text=True, check=True)
    assert image.stdout.strip() == IMAGE
    profile = read('ollama-container-profile.json')
    record = {
        'status': 'revised_phase7_portfolio_gate_passed',
        'generated_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'portfolio-validated synthetic local prototype; not offline-delivered',
        'final_api_image_id': IMAGE,
        'model': profile['model'], 'model_digest': profile['digest'],
        'prompt_sha256': profile['prompt_sha256'],
        'tests': {'passed': 154, 'failed': 0},
        'quality': {'regression_cases': quality['cases'],
                    'answerable': quality['metrics']['answerable_completion'],
                    'uncertainty': quality['metrics']['uncertainty_handling'],
                    'exact_relevant_citations': quality['metrics']['citation_relevant'],
                    'split_limit': 'v6 labels were used to fix relevance; no longer untouched held-out'},
        'load': {'normal_users': 1, 'peak_users': 2,
                 'search_n': load['search']['n'], 'answer_n': load['answer']['n'],
                 'search_p95_seconds': load['search']['p95'],
                 'answer_p95_seconds': load['answer']['p95'],
                 'queue_wait_max_seconds': load['queue_wait_seconds']['max'],
                 'errors': load['errors']},
        'resource': {'samples': resources['samples'],
                     'gpu_used_peak_mib_sampled': resources['host_gpu_used_peak_mib_sampled'],
                     'container_peak_mib_sampled': resources['container_peak_mib_sampled']},
        'network': {'internal': True, 'external_tcp': network['external_tcp'],
                    'packet_capture': False},
        'cold_start': 'first inference timed out; API restart after GPU discovery recovered; unattended reliability pending',
        'project_services_running_after_acceptance': 0,
        'evidence_sha256': {name: digest(name) for name in EVIDENCE},
        'code_sha256': {name: digest(name) for name in CODE},
    }
    OUT.write_text(json.dumps(record, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({'status': record['status'], 'evidence_files': len(EVIDENCE),
                      'project_services_running': 0}))


if __name__ == '__main__':
    main()
