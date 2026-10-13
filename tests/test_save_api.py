"""Authenticated save API over an in-memory ledger and isolated bridge double."""
from copy import deepcopy
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.domain import Actor
from backend.odoo_contract import CONTRACT_VERSION, UPSTREAM_REVISION, Target
from backend.save_operations import MemorySaveLedger, SaveOperations


class BridgeDouble:
    def __init__(self):
        self.receipt=None
        self.calls=0

    def info(self):
        return {'contract_version':CONTRACT_VERSION,'upstream_revision':UPSTREAM_REVISION,
                'atomic_receipt':True,'full_checklist_readback':True}

    def execute(self,envelope):
        self.calls+=1
        self.receipt={'operation_id':envelope['operation_id'],'payload_hash':envelope['payload_hash'],
                      'external_id':42,'payload':deepcopy(envelope['payload'])}
        raise TimeoutError('synthetic lost response')

    def status(self,tenant,company_id,operation_id):
        return deepcopy(self.receipt) if self.receipt and self.receipt['operation_id']==operation_id else None


def test_save_api_separates_actors_and_reconciles_lost_response():
    actors={'technician-token-12345678901':Actor('tech','atlas','technician'),
            'manager-one-token-123456789':Actor('manager','atlas','service_manager'),
            'manager-two-token-123456789':Actor('reviewer','atlas','service_manager'),
            'birch-manager-token-12345678':Actor('other','birch','service_manager')}
    app=create_app(actors)
    service=app.state.service
    service.ingest(actors['technician-token-12345678901'],'sop','SOP','Record the job ID.')
    proposal=service.prepare(actors['technician-token-12345678901'],['sop'],['Record the job ID.'],{'sop':1})
    service.approve(actors['manager-one-token-123456789'],proposal.id,proposal.payload_hash)
    bridge=BridgeDouble()
    app.state.save_ops=SaveOperations(service,MemorySaveLedger(),
        {'atlas':Target(company_id=1,customer_id=2,opportunity_id=3,assignee_id=4)},bridge)
    client=TestClient(app)
    def post(path,token,body):
        return client.post(path,json=body,headers={'Authorization':'Bearer '+token})
    prepared=post('/save-operations/prepare','manager-one-token-123456789',{'proposal_id':proposal.id})
    assert prepared.status_code==201
    op=prepared.json(); identifier=op['id']
    assert op['payload']['steps']==['Record the job ID.']
    assert op['payload']['target']['company_id']==1
    assert op['external_work_completed'] is False
    assert post(f'/save-operations/{identifier}/dispatch','manager-one-token-123456789',{}).json()['error']=='destination_approval_required'
    assert post(f'/save-operations/{identifier}/approve','manager-one-token-123456789',{'payload_hash':op['payload_hash']}).json()['error']=='self_approval'
    assert post(f'/save-operations/{identifier}/approve','manager-two-token-123456789',{'payload_hash':op['payload_hash']}).json()['status']=='approved'
    assert post(f'/save-operations/{identifier}/dispatch','manager-one-token-123456789',{}).json()['status']=='unknown'
    assert post(f'/save-operations/{identifier}/verify','manager-one-token-123456789',{}).json()['status']=='verified'
    replay=post(f'/save-operations/{identifier}/dispatch','manager-one-token-123456789',{}).json()
    assert replay['status']=='verified' and replay['attempts']==1 and bridge.calls==1
    assert replay['external_id']==42 and replay['external_work_completed'] is False
    assert client.get(f'/save-operations/{identifier}',headers={'Authorization':'Bearer birch-manager-token-12345678'}).status_code==404


def test_save_api_disabled_without_explicit_coordinator():
    token='manager-one-token-123456789'
    app=create_app({token:Actor('manager','atlas','service_manager')})
    response=TestClient(app).post('/save-operations/prepare',json={'proposal_id':'proposal'},
                                  headers={'Authorization':'Bearer '+token})
    assert response.status_code==503 and response.json()=={'error':'save_coordinator_unavailable'}
