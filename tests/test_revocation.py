import pytest
from fastapi.testclient import TestClient
from backend.api import create_app
from backend.domain import Actor


def test_live_revocation_blocks_existing_session_and_all_source_paths():
    actors={name:Actor(name,tenant,role) for name,tenant,role in [('tech','atlas','technician'),('manager','atlas','service_manager'),('admin','atlas','administrator'),('other','birch','administrator')]}
    tokens={name:name+'-test-token-01234567890123456789' for name in actors}
    client=TestClient(create_app({tokens[n]:a for n,a in actors.items()}))
    def h(name):return {'Authorization':'Bearer '+tokens[name]}
    assert client.post('/documents',headers=h('tech'),json={'id':'sop','title':'SOP','text':'Record the job ID.'}).status_code==201
    draft=client.post('/checklists',headers=h('tech'),json={'document_ids':['sop'],'steps':['Record the job ID.']}).json()
    assert client.post('/documents/sop/access',headers=h('tech'),json={'actor_id':'manager','revoked':True}).status_code==403
    assert client.post('/documents/sop/access',headers=h('other'),json={'actor_id':'tech','revoked':True}).status_code==404
    assert client.post('/documents/sop/access',headers=h('admin'),json={'actor_id':'tech','revoked':True}).status_code==204
    for endpoint in ['/documents','/search?q=job','/checklists']:
        assert client.get(endpoint,headers=h('tech')).json()==[]
    for endpoint in ['/documents/sop','/documents/sop/versions/1',f"/checklists/{draft['id']}"]:
        assert client.get(endpoint,headers=h('tech')).status_code==404
    assert client.post('/documents',headers=h('tech'),json={'id':'sop','title':'SOP','text':'Overwrite to regain access.'}).status_code==403
    assert client.get(f"/checklists/{draft['id']}",headers=h('manager')).json()['status']=='stale'
    assert client.post('/documents/sop/access',headers=h('admin'),json={'actor_id':'tech','revoked':False}).status_code==204
    assert client.get('/documents/sop',headers=h('tech')).status_code==200
    assert client.get(f"/checklists/{draft['id']}",headers=h('manager')).json()['status']=='stale'
