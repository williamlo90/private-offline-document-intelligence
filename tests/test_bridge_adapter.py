"""Transport doubles only; never contacts Odoo."""
import asyncio
from datetime import datetime, timedelta, timezone
import json
from uuid import uuid4
import httpx
import pytest
from backend.bridge_adapter import BridgeProfile, BridgeFailure, SignedChecklistBridge
from backend.bridge_signing import verify_envelope
from backend.domain import DomainError, Service, MemoryRepository
from backend.odoo_contract import CONTRACT_VERSION, UPSTREAM_REVISION, fingerprint
from backend.save_operations import SaveOperations, MemorySaveLedger

KEY='fixture-signing-key-at-least-thirty-two-characters'
TOKEN='fixture-api-key-at-least-twenty-four'


def profile(**overrides):
    return BridgeProfile(port=18069,database='private_test',tenant='atlas',company_id=1,
                         api_key=TOKEN,signing_key=KEY,**overrides)


def envelope():
    payload={'contract_version':CONTRACT_VERSION,'upstream_revision':UPSTREAM_REVISION,'tenant':'atlas',
             'target':{'company_id':1,'customer_id':2,'opportunity_id':3,'assignee_id':4},
             'proposal_id':str(uuid4()),'proposal_hash':'a'*64,'prepared_by':'tech','reviewed_by':'manager',
             'steps':['Record ID.'],'source_versions':[['sop',1,'b'*64]],'step_sources':[['sop',1,1,0,10]]}
    return {'operation_id':str(uuid4()),'payload_hash':fingerprint(payload),'payload':payload,
            'requested_by':'manager','approved_by':'reviewer','expires_at':(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()}


def test_signed_request_fixed_method_and_scoped_readback():
    calls=[]
    async def handler(request):
        calls.append(request)
        assert request.url.host=='127.0.0.1'
        assert request.headers['X-Odoo-Database']=='private_test'
        body=json.loads(request.content)
        if request.url.path.endswith('/execute'):
            verify_envelope(body['envelope'],body['signature'],KEY.encode(),'atlas',1)
            return httpx.Response(200,json={'external_id':42})
        return httpx.Response(200,content=b'null')
    adapter=SignedChecklistBridge(profile(),transport=httpx.MockTransport(handler))
    assert adapter.execute(envelope())['external_id']==42
    assert adapter.status('atlas',1,str(uuid4())) is None
    assert len(calls)==2
    assert TOKEN not in repr(profile()) and KEY not in repr(profile())


@pytest.mark.parametrize('mode,code',[('timeout','bridge_timeout'),('redirect','bridge_rejected'),
                                   ('large','bridge_response_limit'),('malformed','bridge_malformed'),
                                   ('server_error','bridge_rejected')])
def test_execute_failure_is_unknown_without_retry_or_error_leak(mode,code):
    calls=[]
    async def handler(request):
        calls.append(request)
        if mode=='timeout':await asyncio.sleep(1)
        if mode=='redirect':return httpx.Response(307,headers={'Location':'https://example.com'})
        if mode=='large':return httpx.Response(200,content=b'x'*1000001)
        if mode=='server_error':return httpx.Response(500,content=b'SECRET traceback credentials')
        return httpx.Response(200,content=b'SECRET invalid JSON')
    adapter=SignedChecklistBridge(profile(timeout_seconds=.05),transport=httpx.MockTransport(handler))
    with pytest.raises(BridgeFailure) as error:adapter.execute(envelope())
    assert error.value.code==code and error.value.uncertain
    assert len(calls)==1 and 'SECRET' not in str(error.value)


def test_wrong_scope_and_method_rejected_without_http():
    calls=[]
    def handler(request):calls.append(request);raise AssertionError('must not connect')
    adapter=SignedChecklistBridge(profile(),transport=httpx.MockTransport(handler))
    data=envelope();data['payload']['tenant']='birch';data['payload_hash']=fingerprint(data['payload'])
    with pytest.raises(DomainError):adapter.execute(data)
    with pytest.raises(BridgeFailure):adapter.status('birch',1,str(uuid4()))
    with pytest.raises(BridgeFailure):adapter._call('arbitrary_method',{})
    assert not calls


def test_activity_only_capability_and_memory_coordinator_rejected():
    adapter=SignedChecklistBridge(profile(),transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'contract_version':'1.0'})))
    with pytest.raises(DomainError):adapter.info()
    with pytest.raises(DomainError) as error:
        SaveOperations(Service(MemoryRepository()),MemorySaveLedger(),{},adapter)
    assert error.value.code=='durable_save_coordinator_required'
