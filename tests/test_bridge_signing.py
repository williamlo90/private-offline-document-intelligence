from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
from backend.bridge_signing import sign_envelope, verify_envelope
from backend.domain import DomainError
from backend.odoo_contract import CONTRACT_VERSION, UPSTREAM_REVISION, fingerprint

KEY=b'isolated-test-key-with-at-least-32-bytes'


def envelope():
    payload={'contract_version':CONTRACT_VERSION,'upstream_revision':UPSTREAM_REVISION,
             'tenant':'atlas','target':{'company_id':1,'customer_id':2,'opportunity_id':3,'assignee_id':4},
             'proposal_id':str(uuid4()),'proposal_hash':'a'*64,'prepared_by':'tech','reviewed_by':'manager',
             'steps':['Record ID.'],'source_versions':[['sop',1,'b'*64]],'step_sources':[['sop',1,1,0,10]]}
    return {'operation_id':str(uuid4()),'payload_hash':fingerprint(payload),'payload':payload,
            'requested_by':'manager','approved_by':'reviewer','expires_at':(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat()}


def test_signed_envelope_canonical_and_immutable_return():
    data=envelope();signature=sign_envelope(data,KEY)
    assert sign_envelope(dict(reversed(list(data.items()))),KEY)==signature
    result=verify_envelope(data,signature,KEY,'atlas',1)
    result['payload']['steps'].append('altered')
    assert data['payload']['steps']==['Record ID.']


@pytest.mark.parametrize('field',['target','steps','approval','operation'])
def test_unsigned_change_rejected(field):
    data=envelope();signature=sign_envelope(data,KEY)
    if field=='target':data['payload']['target']['company_id']=2
    if field=='steps':data['payload']['steps']=['Altered']
    if field=='approval':data['approved_by']='manager'
    if field=='operation':data['operation_id']=str(uuid4())
    with pytest.raises(DomainError) as error:verify_envelope(data,signature,KEY,'atlas',1)
    assert error.value.code=='invalid_signature'


@pytest.mark.parametrize('change,code',[('tenant','scope_mismatch'),('expired','save_approval_expired'),('self','self_approval'),('hash','invalid_bridge_envelope')])
def test_signature_does_not_bypass_business_scope(change,code):
    data=envelope()
    if change=='expired':data['expires_at']='2000-01-01T00:00:00+00:00'
    if change=='self':data['approved_by']=data['requested_by']
    if change=='hash':data['payload_hash']='0'*64
    with pytest.raises(DomainError) as error:
        verify_envelope(data,sign_envelope(data,KEY),KEY,'birch' if change=='tenant' else 'atlas',1)
    assert error.value.code==code
