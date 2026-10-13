from pathlib import Path
import hashlib
import json
import pytest
from backend.document_worker import DocumentWorker,WatchedSource,checkpoint_lock
from backend.domain import Service,MemoryRepository,Actor,DomainError
from backend.pdf_parser import ParseError,ParsedPDF,Page

ACTOR=Actor('tech','atlas','technician')


def fixture(tmp_path,parser=None,sources=None):
    service=Service(MemoryRepository())
    (tmp_path/'source.pdf').write_bytes(b'%PDF-fixture')
    kwargs={'parser':parser} if parser else {}
    worker=DocumentWorker(service,ACTOR,tmp_path,tmp_path/'checkpoint.json',sources or [WatchedSource('sop','source.pdf','SOP')],**kwargs)
    return service,worker


def parsed(data,language):
    return ParsedPDF(hashlib.sha256(data).hexdigest(),(Page(1,'Record the job ID.'),))


def test_native_pdf_ingest_restart_and_change(tmp_path):
    service,worker=fixture(tmp_path)
    corpus=Path(__file__).resolve().parents[1]/'evaluation/development'
    (tmp_path/'source.pdf').write_bytes((corpus/'atlas-backup-v1.pdf').read_bytes())
    assert worker.run_once()['entries']['sop']['status']=='done'
    assert service.read_document(ACTOR,'sop').version==1
    worker.run_once();assert service.read_document(ACTOR,'sop').version==1
    (tmp_path/'source.pdf').write_bytes((corpus/'birch-disk-v1.pdf').read_bytes())
    worker.run_once();assert service.read_document(ACTOR,'sop').version==2
    # Checkpoint cannot hide lost memory repository contents after an API restart.
    worker.service=Service(MemoryRepository())
    assert worker.run_once()['entries']['sop']['status']=='done'
    assert worker.service.read_document(ACTOR,'sop').version==1


def test_retry_budget_and_metadata_only_checkpoint(tmp_path):
    calls=[]
    def busy(data,language):calls.append(1);raise ParseError('parser_busy')
    _,worker=fixture(tmp_path,busy);now=[100.0];worker.clock=lambda:now[0]
    worker.run_once();worker.run_once();assert len(calls)==1
    now[0]+=10;worker.run_once();now[0]+=10
    result=worker.run_once()
    assert result['entries']['sop']['status']=='review' and len(calls)==3
    now[0]+=100;worker.run_once();assert len(calls)==3
    text=(tmp_path/'checkpoint.json').read_text()
    assert '%PDF' not in text and 'Record the job' not in text


def test_scope_and_missing_source_do_not_parse_or_delete(tmp_path):
    service,worker=fixture(tmp_path,parsed)
    worker.run_once()
    service.change_access(Actor('admin','atlas','administrator'),ACTOR,'sop',True)
    worker.parser=lambda *args:pytest.fail('revoked source must not parse')
    assert worker.run_once()['entries']['sop']['error']=='forbidden'
    service.change_access(Actor('admin','atlas','administrator'),ACTOR,'sop',False)
    (tmp_path/'source.pdf').unlink()
    assert worker.run_once()['entries']['sop']['error']=='source_missing'
    assert service.read_document(ACTOR,'sop').version==1


def test_source_path_escape_and_worker_lock(tmp_path):
    _,worker=fixture(tmp_path,parsed,[WatchedSource('sop','../outside.pdf','SOP')])
    assert worker.run_once()['entries']['sop']['error']=='unsafe_source_path'
    with checkpoint_lock(tmp_path/'checkpoint.lock'):
        with pytest.raises(DomainError) as error:worker.run_once()
    assert error.value.code=='worker_busy'


def test_queue_bound_and_identity_checkpoint(tmp_path):
    service,worker=fixture(tmp_path,parsed,[WatchedSource(f'd{i}','source.pdf',f'Doc {i}') for i in range(12)])
    assert len(worker.run_once()['entries'])==10
    assert len(service.list_documents(ACTOR))==10
    worker.run_once();assert len(service.list_documents(ACTOR))==12
    worker.actor=Actor('other','birch','technician')
    with pytest.raises(DomainError):worker.run_once()


def test_source_changes_during_parse_are_not_ingested(tmp_path):
    def mutate(data,language):
        (tmp_path/'source.pdf').write_bytes(b'%PDF-new')
        return parsed(data,language)
    service,worker=fixture(tmp_path,mutate)
    assert worker.run_once()['entries']['sop']['error']=='source_changed'
    assert service.list_documents(ACTOR)==[]
