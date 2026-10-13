import json

from fastapi.testclient import TestClient
import pytest

from backend.api import create_app
from backend.domain import Actor


@pytest.fixture
def lab():
    actors = {'tech': Actor('tech', 'atlas', 'technician'),
              'manager': Actor('manager', 'atlas', 'service_manager'),
              'other': Actor('other', 'birch', 'technician'),
              'limited': Actor('limited', 'atlas', 'service_manager', frozenset({'other-doc'})),
              'admin': Actor('admin', 'atlas', 'administrator'),
              'auditor': Actor('auditor', 'atlas', 'auditor')}
    tokens = {name: name + '-fixture-token-01234567890123456789' for name in actors}
    client = TestClient(create_app({tokens[name]: actor for name, actor in actors.items()}))
    def headers(name):
        return {'Authorization': f'Bearer {tokens[name]}'}
    result = client.post('/documents', headers=headers('tech'), json={'id': 'backup', 'title': 'Backup SOP', 'text': 'Check backup status. Record the job ID.'})
    assert result.status_code == 201
    return client, headers


def proposal(client, headers, actor='tech'):
    result = client.post('/checklists', headers=headers(actor), json={'document_ids': ['backup'], 'steps': ['Check backup status.']})
    assert result.status_code == 201, result.text
    return result.json()


def test_source_review_queue_uses_current_document_grants(lab):
    client,headers=lab
    client.app.state.service.ingest(Actor('tech','atlas','technician'),'future','Future SOP',
        'Check recovery.',effective='2099-01-01')
    atlas=client.get('/source-reviews',headers=headers('tech'))
    assert atlas.status_code==200
    assert {'document_id':'future','version':1,'reasons':['future'],'available':True} in atlas.json()
    assert client.get('/source-reviews',headers=headers('other')).json()==[]
    assert client.get('/source-reviews',headers=headers('limited')).json()==[]


def test_ingest_review_and_sanitized_audit(lab):
    client, headers = lab
    draft = proposal(client, headers)
    result = client.post(f"/checklists/{draft['id']}/approve", headers=headers('manager'), json={'payload_hash': draft['payload_hash']})
    assert result.status_code == 200
    assert result.json()['status'] == 'approved'
    events = client.get('/audit', headers=headers('auditor')).json()
    assert [e['action'] for e in events] == ['document_ingested', 'checklist_prepared', 'checklist_approved']
    assert 'Check backup' not in json.dumps(events)
    assert 'fixture-token' not in json.dumps(events)


@pytest.mark.parametrize('actor', ['other', 'limited'])
def test_document_and_proposal_access_is_scoped(lab, actor):
    client, headers = lab
    draft = proposal(client, headers)
    assert client.get('/documents', headers=headers(actor)).json() == []
    assert client.get('/documents/backup', headers=headers(actor)).status_code == 404
    assert client.get(f"/checklists/{draft['id']}", headers=headers(actor)).status_code == 404
    assert client.post('/checklists', headers=headers(actor), json={'document_ids': ['backup'], 'steps': ['Check backup status.']}).status_code == 404


def test_admin_does_not_inherit_business_access(lab):
    client, headers = lab
    assert client.get('/documents', headers=headers('admin')).status_code == 403
    assert client.post('/documents', headers=headers('admin'), json={'id': 'x', 'title': 'x', 'text': 'secret'}).status_code == 403


def test_self_approval_and_replay_rejected(lab):
    client, headers = lab
    draft = proposal(client, headers, 'manager')
    assert client.post(f"/checklists/{draft['id']}/approve", headers=headers('manager'), json={'payload_hash': draft['payload_hash']}).status_code == 403
    draft = proposal(client, headers)
    for expected in [200, 409]:
        assert client.post(f"/checklists/{draft['id']}/approve", headers=headers('manager'), json={'payload_hash': draft['payload_hash']}).status_code == expected


def test_source_drift_invalidates_approval(lab):
    client, headers = lab
    draft = proposal(client, headers)
    assert client.post(f"/checklists/{draft['id']}/approve", headers=headers('manager'), json={'payload_hash': draft['payload_hash']}).status_code == 200
    client.post('/documents', headers=headers('tech'), json={'id': 'backup', 'title': 'Backup SOP', 'text': 'Stop and contact service manager.'})
    result = client.get(f"/checklists/{draft['id']}", headers=headers('manager')).json()
    assert result['status'] == 'stale'
    assert result['approver_id'] is None
    assert client.post(f"/checklists/{draft['id']}/approve", headers=headers('manager'), json={'payload_hash': draft['payload_hash']}).status_code == 409


def test_forged_identity_unknown_fields_and_sensitive_error_redaction(lab):
    client, headers = lab
    assert client.get('/documents').status_code == 401
    body = {'id': 'stolen', 'title': 'Secret', 'text': 'sensitive-document-body', 'tenant': 'birch'}
    response = client.post('/documents', headers=headers('tech'), json=body)
    assert response.status_code == 422
    assert 'sensitive-document-body' not in response.text
    assert client.get('/documents', headers={'Authorization': 'Bearer forged'}).status_code == 401


def test_unsupported_steps_and_wrong_payload_rejected(lab):
    client, headers = lab
    response = client.post('/checklists', headers=headers('tech'), json={'document_ids': ['backup'], 'steps': ['Delete all backups.']})
    assert response.status_code == 422
    draft = proposal(client, headers)
    assert client.post(f"/checklists/{draft['id']}/approve", headers=headers('manager'), json={'payload_hash': '0' * 64}).status_code == 409


def test_review_queue_filters_object_and_tenant_access(lab):
    client, headers = lab
    draft = proposal(client, headers)
    assert client.get('/checklists', headers=headers('manager')).json()[0]['id'] == draft['id']
    for actor in ('limited', 'other'):
        assert client.get('/checklists', headers=headers(actor)).json() == []
    response = client.get('/documents/backup', headers=headers('tech'))
    assert response.headers['Cache-Control'] == 'no-store'
    assert "frame-ancestors 'none'" in response.headers['Content-Security-Policy']
