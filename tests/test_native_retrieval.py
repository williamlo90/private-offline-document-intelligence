from datetime import date
import hashlib
import re

from fastapi.testclient import TestClient

from backend.api import create_app
from backend.domain import Actor, MemoryRepository, Service
from backend.native_retrieval import NativeVectorIndex


class TinyEncoder:
    """Deterministic contract double; native model quality is measured separately."""
    def embed(self, texts):
        result=[]
        for text in texts:
            vector=[0.0]*384
            for word in set(re.findall(r'\w+',text.lower())):
                vector[int(hashlib.sha256(word.encode()).hexdigest(),16)%384]+=1.0
            result.append(vector)
        return result


def test_current_permissions_version_and_deletion_in_native_index():
    repo=MemoryRepository();service=Service(repo);index=NativeVectorIndex(TinyEncoder(),'fixture-revision')
    tech=Actor('tech','atlas','technician');admin=Actor('admin','atlas','administrator')
    manager=Actor('manager','atlas','service_manager')
    birch=Actor('other','birch','technician')
    service.ingest(tech,'guide','Guide','Check backup status.')
    service.ingest(birch,'secret','Secret','Check backup status. Confidential Birch.')
    results=index.search(service,tech,'backup',date(2026,10,12))
    assert [r['document_id'] for r in results]==['guide']
    assert results[0]['quote']=='Check backup status.'
    assert results[0]['model_revision']=='fixture-revision'
    assert index.search(service,birch,'backup')[0]['document_id']=='secret'
    service.change_access(admin,tech,'guide',True)
    assert index.search(service,tech,'backup')==[]
    assert ('atlas','guide') in index.entries  # Cache is never an authorization source.
    service.change_access(admin,tech,'guide',False)
    service.ingest(tech,'guide','Guide','Check updated backup status.')
    results=index.search(service,tech,'updated')
    assert len(results)==1 and results[0]['version']==2
    assert ('atlas','guide') in index.entries
    service.delete(manager,'guide')
    assert index.search(service,tech,'backup')==[]
    assert ('atlas','guide') not in index.entries
    assert ('birch','secret') in index.entries


def test_semantic_endpoint_uses_current_actor_scope():
    token='test-native-semantic-token-0123456789'
    actor=Actor('tech','atlas','technician')
    app=create_app({token:actor})
    app.state.semantic=NativeVectorIndex(TinyEncoder(),'fixture-revision')
    client=TestClient(app)
    headers={'Authorization':'Bearer '+token}
    client.post('/documents',json={'id':'guide','title':'Guide','text':'Check backup status.'},headers=headers)
    result=client.get('/semantic-search?q=backup',headers=headers)
    assert result.status_code==200
    assert result.json()[0]['quote']=='Check backup status.'
    assert client.get('/semantic-search?q=backup').status_code==401
    client.delete('/documents/guide',headers=headers)  # Technician cannot delete.
    assert client.get('/semantic-search?q=backup',headers=headers).json()[0]['version']==1
