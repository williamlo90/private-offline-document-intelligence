from contextlib import contextmanager
from pathlib import Path
import pytest
from pglast import parse_sql
from backend.domain import Actor, DomainError
from backend.save_repository import PostgresSaveRepository


class ConnectionDouble:
    def __init__(self,row=None,commit_failure=False):
        self.row=row;self.commit_failure=commit_failure;self.committed=False;self.statements=[]
    @contextmanager
    def transaction(self):
        yield
        if self.commit_failure:raise OSError('simulated commit failure')
        self.committed=True
    @contextmanager
    def cursor(self):yield self
    def execute(self,sql,params):self.statements.append((sql,params))
    def fetchone(self):return self.row


def test_dispatch_claim_returns_only_after_commit():
    connection=ConnectionDouble(('op',2,{},'a'*64))
    result=PostgresSaveRepository(connection).claim_dispatch(Actor('manager','atlas','service_manager'),'op',1,'a'*64)
    assert connection.committed and result[1]==2
    assert connection.statements[0][1]==('atlas','manager')
    assert connection.statements[1][1]==('atlas','op',1,'a'*64)
    assert "attempts=0" in connection.statements[1][0]


def test_unclaimed_or_failed_commit_never_returns_dispatch_permission():
    actor=Actor('manager','atlas','service_manager')
    connection=ConnectionDouble()
    with pytest.raises(DomainError):PostgresSaveRepository(connection).claim_dispatch(actor,'op',1,'a'*64)
    assert not connection.committed
    connection=ConnectionDouble(('op',2,{},'a'*64),True)
    with pytest.raises(OSError):PostgresSaveRepository(connection).claim_dispatch(actor,'op',1,'a'*64)
    assert not connection.committed


def test_dispatch_claim_denies_wrong_role_before_sql():
    connection=ConnectionDouble()
    with pytest.raises(DomainError):PostgresSaveRepository(connection).claim_dispatch(Actor('tech','atlas','technician'),'op',1,'a'*64)
    assert not connection.statements


def test_save_migration_syntax_only():
    sql=(Path(__file__).resolve().parents[1]/'migrations/003_save_operations.sql').read_text()
    assert len(parse_sql(sql))==6


def test_approval_and_readback_use_revision_scope_and_separate_actor():
    actor=Actor('reviewer','atlas','service_manager')
    connection=ConnectionDouble(('op',2,{},'a'*64))
    repository=PostgresSaveRepository(connection)
    repository.approve(actor,'op',1,'a'*64)
    sql,params=connection.statements[-1]
    assert 'requested_by<>%s' in sql and "payload->>'prepared_by'<>%s" in sql
    assert params==('reviewer','atlas','op',1,'a'*64,'reviewer','reviewer')
    repository.record_readback(actor,'op',2,status='verified',external_id=42)
    assert connection.statements[-1][1]==('verified',42,None,'atlas','op',2)
    count=len(connection.statements)
    with pytest.raises(DomainError):repository.record_readback(actor,'op',3,status='verified',external_id=True)
    with pytest.raises(DomainError):repository.record_readback(actor,'op',3,status='unknown',error='secret traceback')
    assert len(connection.statements)==count


def test_preview_unique_insert_and_payload_validation():
    from datetime import datetime,timezone,timedelta
    from dataclasses import replace
    from backend.odoo_contract import canonical,fingerprint
    from backend.save_operations import SaveOperation
    actor=Actor('manager','atlas','service_manager')
    payload={'tenant':'atlas','proposal_id':'proposal'}
    operation=SaveOperation('op','atlas','proposal',actor,canonical(payload),fingerprint(payload),datetime.now(timezone.utc)+timedelta(minutes=10))
    connection=ConnectionDouble(('op',0,payload,fingerprint(payload)))
    repository=PostgresSaveRepository(connection)
    repository.insert_preview(actor,operation)
    assert 'ON CONFLICT (tenant_id,proposal_id) DO NOTHING' in connection.statements[-1][0]
    assert connection.committed
    count=len(connection.statements)
    with pytest.raises(DomainError):repository.insert_preview(actor,replace(operation,payload_hash='0'*64))
    assert len(connection.statements)==count
    with pytest.raises(DomainError):PostgresSaveRepository(ConnectionDouble()).insert_preview(actor,operation)


@pytest.mark.parametrize('method,args,kwargs',[
    ('read',('op',),{}),('approve',('op',1,'a'*64),{}),
    ('record_readback',('op',1),{'status':'unknown','error':'receipt_not_found'})])
def test_repository_missing_rows_fail_without_success(method,args,kwargs):
    connection=ConnectionDouble()
    with pytest.raises(DomainError):
        getattr(PostgresSaveRepository(connection),method)(Actor('manager','atlas','service_manager'),*args,**kwargs)
    assert not connection.committed
