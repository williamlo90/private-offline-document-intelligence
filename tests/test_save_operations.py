"""Memory-ledger and bridge-double evidence, not durable/live Odoo acceptance."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
import pytest
from backend.domain import Actor, Service, MemoryRepository, DomainError
from backend.odoo_contract import Target, CONTRACT_VERSION, UPSTREAM_REVISION
from backend.save_operations import SaveOperations, MemorySaveLedger


class BridgeDouble:
    def __init__(self):
        self.receipts={};self.calls=0;self.lose_response=False;self.no_effect=False
    def info(self):
        return {'contract_version':CONTRACT_VERSION,'upstream_revision':UPSTREAM_REVISION,
                'atomic_receipt':True,'full_checklist_readback':True}
    def execute(self, envelope):
        self.calls+=1
        if not self.no_effect:
            self.receipts[envelope['operation_id']]={'operation_id':envelope['operation_id'],
                'payload_hash':envelope['payload_hash'],'external_id':42,'payload':deepcopy(envelope['payload'])}
        if self.lose_response:raise TimeoutError('do not expose secret traceback')
        return {'external_id':42}
    def status(self, tenant, company, identifier):
        return deepcopy(self.receipts.get(identifier))


@pytest.fixture
def lab():
    service=Service(MemoryRepository());tech=Actor('tech','atlas','technician')
    manager=Actor('manager','atlas','service_manager');reviewer=Actor('reviewer','atlas','service_manager')
    service.ingest(tech,'sop','SOP','Record the job ID.')
    draft=service.prepare(tech,['sop'],['Record the job ID.'],{'sop':1})
    service.approve(manager,draft.id,draft.payload_hash)
    bridge=BridgeDouble()
    operations=SaveOperations(service,MemorySaveLedger(),{'atlas':Target(company_id=1,customer_id=2,opportunity_id=3,assignee_id=4)},bridge)
    op=operations.prepare(manager,draft.id)
    return service,manager,reviewer,bridge,operations,op


def approved(lab):
    _,manager,reviewer,bridge,ops,op=lab
    ops.approve(reviewer,op.id,op.payload_hash)
    return manager,bridge,ops,op


def test_separate_destination_approval_and_replay(lab):
    _,manager,reviewer,bridge,ops,op=lab
    with pytest.raises(DomainError):ops.save(manager,op.id)
    with pytest.raises(DomainError):ops.approve(manager,op.id,op.payload_hash)
    with pytest.raises(DomainError):ops.approve(reviewer,op.id,'0'*64)
    ops.approve(reviewer,op.id,op.payload_hash)
    assert ops.save(manager,op.id).status=='verified'
    assert ops.save(manager,op.id).external_id==42 and bridge.calls==1
    assert ops.prepare(manager,op.proposal_id).id==op.id


def test_lost_response_recovers_without_second_effect(lab):
    manager,bridge,ops,op=approved(lab);bridge.lose_response=True
    assert ops.save(manager,op.id).status=='unknown'
    assert ops.save(manager,op.id).status=='verified'
    assert bridge.calls==1


def test_missing_receipt_never_triggers_blind_retry(lab):
    manager,bridge,ops,op=approved(lab);bridge.no_effect=True;bridge.lose_response=True
    assert ops.save(manager,op.id).status=='unknown'
    result=ops.save(manager,op.id)
    assert result.status=='unknown' and result.error=='receipt_not_found' and bridge.calls==1


def test_readback_mismatch_requires_review(lab):
    manager,bridge,ops,op=approved(lab);bridge.lose_response=True
    ops.save(manager,op.id)
    bridge.receipts[op.id]['payload']['target']['company_id']=99
    assert ops.reconcile(manager,op.id).status=='review'
    with pytest.raises(DomainError):ops.save(manager,op.id)
    with pytest.raises(DomainError):ops.approve(lab[2],op.id,op.payload_hash)
    assert bridge.calls==1


@pytest.mark.parametrize('mutation',['source','target','expiry','reviewer_access'])
def test_changes_block_dispatch(lab,mutation):
    service,manager,reviewer,bridge,ops,op=lab
    approved(lab)
    if mutation=='source':service.ingest(manager,'sop','SOP','Changed instructions.')
    if mutation=='target':ops.targets['atlas']=Target(company_id=99,customer_id=2,opportunity_id=3,assignee_id=4)
    if mutation=='expiry':ops.clock=lambda:op.expires_at+timedelta(seconds=1)
    if mutation=='reviewer_access':service.change_access(Actor('admin','atlas','administrator'),reviewer,'sop',True)
    with pytest.raises(DomainError):ops.save(manager,op.id)
    assert bridge.calls==0


def test_reconcile_is_scoped_and_survives_expiry(lab):
    manager,bridge,ops,op=approved(lab);bridge.lose_response=True
    ops.save(manager,op.id)
    ops.clock=lambda:op.expires_at+timedelta(seconds=1)
    with pytest.raises(DomainError):ops.reconcile(Actor('other','birch','service_manager'),op.id)
    assert ops.reconcile(manager,op.id).status=='verified'


def test_concurrent_duplicate_calls_have_one_dispatch_in_memory_harness(lab):
    manager,bridge,ops,op=approved(lab)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:ops.save(manager,op.id),range(2)))
    assert all(r.status=='verified' for r in results)
    assert bridge.calls==1
