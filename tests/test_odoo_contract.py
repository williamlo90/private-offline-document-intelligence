from copy import deepcopy
import pytest
from backend.domain import Actor, Service, MemoryRepository, DomainError
from backend.odoo_contract import Target, prepare_save_payload, require_capability, verify_receipt, CONTRACT_VERSION, UPSTREAM_REVISION


def preview():
    service=Service(MemoryRepository())
    tech=Actor('tech','atlas','technician'); manager=Actor('manager','atlas','service_manager')
    step='Record the incident identifier, customer reference, backup job identifier and original evidence location before requesting a second technician to review the backup restoration procedure.'
    service.ingest(tech,'sop','SOP',step)
    proposal=service.prepare(tech,['sop'],[step],{'sop':1})
    service.approve(manager,proposal.id,proposal.payload_hash)
    target=Target(company_id=1,customer_id=11,opportunity_id=12,assignee_id=13)
    return service,manager,proposal,target,step


def test_full_checklist_preserved_and_destination_bound():
    service,manager,proposal,target,step=preview()
    result=prepare_save_payload(service,manager,proposal.id,target)
    assert result['payload']['steps']==[step] and len(step)>120
    assert result['status']=='destination_review_required'
    other=target.model_copy(update={'company_id':2})
    assert result['payload_hash'] != prepare_save_payload(service,manager,proposal.id,other)['payload_hash']
    assert not any(e['action']=='odoo_saved' for e in service.repo.events('atlas'))


def test_upstream_contract_fails_closed():
    with pytest.raises(DomainError):require_capability({'contract_version':'1.0'})
    require_capability({'contract_version':CONTRACT_VERSION,'upstream_revision':UPSTREAM_REVISION,'atomic_receipt':True,'full_checklist_readback':True})


@pytest.mark.parametrize('change',['scope','content','hash','operation','id'])
def test_readback_requires_exact_scope_and_content(change):
    service,manager,proposal,target,_=preview()
    result=prepare_save_payload(service,manager,proposal.id,target)
    receipt={'operation_id':'op-1','payload_hash':result['payload_hash'],'external_id':42,'payload':deepcopy(result['payload'])}
    assert verify_receipt(receipt,'op-1',result['payload'])==42
    if change=='scope':receipt['payload']['target']['company_id']=2
    if change=='content':receipt['payload']['steps']=['truncated']
    if change=='hash':receipt['payload_hash']='0'*64
    if change=='operation':receipt['operation_id']='other'
    if change=='id':receipt['external_id']=True
    with pytest.raises(DomainError):verify_receipt(receipt,'op-1',result['payload'])


def test_stale_or_cross_tenant_cannot_prepare_save():
    service,manager,proposal,target,_=preview()
    with pytest.raises(DomainError):prepare_save_payload(service,Actor('other','birch','service_manager'),proposal.id,target)
    service.ingest(manager,'sop','SOP','Changed source')
    with pytest.raises(DomainError) as error:prepare_save_payload(service,manager,proposal.id,target)
    assert error.value.code=='approved_checklist_required'
