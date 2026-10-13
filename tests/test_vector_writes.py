from contextlib import contextmanager
import pytest
from backend.domain import Actor,Service,MemoryRepository,DomainError
from backend.vector_adapter import PgVectorSearch

class Connection:
    def __init__(self,version=1):self.calls=[];self.version=version;self.commits=0;self.rollbacks=0;self.fail_insert=False
    @contextmanager
    def transaction(self):
        try:yield
        except Exception:self.rollbacks+=1;raise
        else:self.commits+=1
    def execute(self,sql,params):
        self.calls.append((sql,params))
        if self.fail_insert and sql.startswith('INSERT'):raise RuntimeError('simulated_db_failure')
        return self
    def fetchone(self):return (self.version,)

def lab():
    service=Service(MemoryRepository());actor=Actor('t','atlas','technician')
    service.ingest(actor,'d','D','Check backup.')
    chunk={'page':1,'start':0,'end':13,'quote':'Check backup.','embedding':[0.1]*384}
    return service,actor,chunk

def test_replace_is_scoped_and_uses_single_transaction():
    service,actor,chunk=lab();conn=Connection();adapter=PgVectorSearch(conn,'model@sha')
    assert adapter.replace_index(service,actor,'d',1,[chunk])['indexed_chunks']==1
    assert conn.commits==1
    assert [p for q,p in conn.calls if q.startswith('DELETE')]==[('atlas','d','model@sha')]
    assert any('FOR UPDATE' in q for q,p in conn.calls)
    assert conn.calls[-1][1][:3]==('atlas','d',1)

def test_invalid_or_foreign_source_never_writes():
    service,actor,chunk=lab();conn=Connection();adapter=PgVectorSearch(conn,'model@sha')
    with pytest.raises(DomainError):adapter.replace_index(service,Actor('b','birch','technician'),'d',1,[chunk])
    with pytest.raises(DomainError):adapter.replace_index(service,actor,'d',1,[{**chunk,'quote':'fabricated'}])
    with pytest.raises(ValueError):adapter.replace_index(service,actor,'d',1,[chunk,chunk])
    assert conn.calls==[]

def test_db_drift_and_insert_failure_leave_transaction_uncommitted():
    service,actor,chunk=lab();conn=Connection(version=2);adapter=PgVectorSearch(conn,'model@sha')
    with pytest.raises(DomainError):adapter.replace_index(service,actor,'d',1,[chunk])
    assert not any(q.startswith('DELETE') for q,p in conn.calls)
    conn=Connection();conn.fail_insert=True
    with pytest.raises(RuntimeError):PgVectorSearch(conn,'model@sha').replace_index(service,actor,'d',1,[chunk])
    assert conn.commits==0 and conn.rollbacks==1

def test_delete_requires_manager_and_scopes_all_model_revisions():
    service,actor,chunk=lab();conn=Connection();adapter=PgVectorSearch(conn,'model@sha')
    with pytest.raises(DomainError):adapter.delete_index(service,actor,'d')
    adapter.delete_index(service,Actor('m','atlas','service_manager'),'d')
    assert conn.calls[-1][1]==('atlas','d') and conn.commits==1
