import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from backend.api import create_app
from backend.domain import Actor, DomainError, MemoryRepository, Service
from backend.skills import AuditReadiness, BusinessSkills, PrepareChecklist, schemas


@pytest.fixture
def context(tmp_path):
    service = Service(MemoryRepository())
    tech = Actor('tech', 'atlas', 'technician')
    admin = Actor('admin', 'atlas', 'administrator')
    service.ingest(tech, 'sop', 'SOP', 'Record the job ID.')
    return service, BusinessSkills(service, tmp_path), tech, admin


def request():
    return PrepareChecklist(document_ids=['sop'], steps=['Record the job ID.'], expected_versions={'sop': 1})


def test_skill_reuses_scope_versions_and_review_rules(context):
    service, skills, tech, admin = context
    proposal = skills.prepare_service_checklist(tech, request())
    assert proposal.status == 'review' and proposal.approver_id is None
    assert proposal.step_sources == (('sop', 1, 1, 0, 18),)
    with pytest.raises(DomainError) as denied:
        skills.prepare_service_checklist(Actor('other', 'birch', 'technician'), request())
    assert denied.value.code == 'document_not_found'
    service.ingest(tech, 'sop', 'SOP', 'Record the job ID. Contact the manager.')
    with pytest.raises(DomainError) as stale:
        skills.prepare_service_checklist(tech, request())
    assert stale.value.code == 'source_changed_or_expired'
    assert len(service.repo.proposals('atlas')) == 1


def manifest(root, artifacts):
    (root/'manifest.json').write_text(json.dumps({'schema_version':'1.0','artifacts':artifacts}), encoding='utf-8')


def test_readiness_hashes_assets_but_never_claims_offline(context, tmp_path):
    _, skills, tech, admin = context
    assert skills.audit_offline_readiness(admin, AuditReadiness()).status == 'manifest_missing'
    data=b'local synthetic asset'
    (tmp_path/'asset.bin').write_bytes(data)
    manifest(tmp_path,[{'id':'asset','path':'asset.bin','sha256':hashlib.sha256(data).hexdigest()}])
    result=skills.audit_offline_readiness(admin, AuditReadiness())
    assert result.status == 'assets_verified' and result.offline_validated is False
    assert 'isolated_network_boundary' in result.pending
    (tmp_path/'asset.bin').write_bytes(b'changed')
    assert skills.audit_offline_readiness(admin, AuditReadiness()).checks[0].status == 'checksum_mismatch'
    with pytest.raises(DomainError) as denied:
        skills.audit_offline_readiness(tech, AuditReadiness())
    assert denied.value.code == 'forbidden'


def test_readiness_rejects_traversal_cancel_and_untrusted_fields(context, tmp_path):
    _, skills, _, admin = context
    manifest(tmp_path,[{'id':'escape','path':'../outside','sha256':'0'*64}])
    result=skills.audit_offline_readiness(admin, AuditReadiness())
    assert result.checks[0].status == 'missing_or_unsafe'
    assert 'outside' not in result.model_dump_json()
    with pytest.raises(DomainError) as cancelled:
        skills.audit_offline_readiness(admin, AuditReadiness(), cancelled=lambda:True)
    assert cancelled.value.code == 'operation_cancelled'
    (tmp_path/'manifest.json').write_text('{"schema_version":"1.0","offline_validated":true,"artifacts":[]}')
    assert skills.audit_offline_readiness(admin, AuditReadiness()).status == 'manifest_invalid'


def test_http_skill_identity_and_strict_version_contract(context):
    service, _, tech, admin = context
    token='skill-test-token-01234567890123456789'
    client=TestClient(create_app({token:tech}, service.repo))
    headers={'Authorization':f'Bearer {token}'}
    body=request().model_dump()
    response=client.post('/skills/prepare_service_checklist',headers=headers,json=body)
    assert response.status_code == 201 and response.json()['status']=='review'
    assert client.post('/skills/prepare_service_checklist',headers=headers,json={**body,'tenant':'birch'}).status_code==422
    del body['expected_versions']
    assert client.post('/skills/prepare_service_checklist',headers=headers,json=body).status_code==422
    assert client.post('/skills/audit_offline_readiness',headers=headers,json={}).status_code==403
    assert client.post('/skills/audit_offline_readiness',headers=headers,json={'path':'C:/'}).status_code==422


def test_published_schemas_match_bindings():
    root=Path(__file__).resolve().parents[1]
    for name, contract in schemas().items():
        published=json.loads((root/'skills'/name/'schema.json').read_text(encoding='utf-8'))
        assert published == {'schema_version':'1.0',**contract}
