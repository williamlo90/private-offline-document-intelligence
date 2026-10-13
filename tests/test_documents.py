from datetime import date
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfWriter

from backend.domain import Actor, DomainError, MemoryRepository, Service
from backend.pdf_parser import MAX_BYTES, Page, ParseError, parse_pdf

ROOT = Path(__file__).resolve().parents[1]


def test_real_pdf_pages_and_byte_hash():
    source = ROOT/'evaluation/development/atlas-sla-v1.pdf'
    parsed = parse_pdf(source.read_bytes())
    assert len(parsed.pages) == 2
    assert '60 minutes' in parsed.pages[1].text
    assert all(p.method == 'text' for p in parsed.pages)
    assert len(parsed.sha256) == 64


@pytest.mark.parametrize('data,code',[(b'not a pdf','invalid_pdf'),(b'%PDF-'+b'x'*MAX_BYTES,'file_too_large'),(b'%PDF-1.4\nbroken','invalid_pdf')],ids=['wrong-magic','oversized','malformed'])
def test_bad_files_rejected(data, code):
    with pytest.raises(ParseError) as error: parse_pdf(data)
    assert error.value.code == code


def test_encrypted_and_page_limit_rejected():
    writer=PdfWriter();writer.add_blank_page(width=100,height=100);writer.encrypt('secret')
    out=BytesIO();writer.write(out)
    with pytest.raises(ParseError) as error: parse_pdf(out.getvalue())
    assert error.value.code == 'encrypted_pdf'
    writer=PdfWriter()
    for _ in range(31):writer.add_blank_page(width=100,height=100)
    out=BytesIO();writer.write(out)
    with pytest.raises(ParseError) as error:parse_pdf(out.getvalue())
    assert error.value.code == 'page_limit'


def test_history_deletion_and_current_permissions():
    service=Service(MemoryRepository()); tech=Actor('t','atlas','technician'); manager=Actor('m','atlas','service_manager')
    service.ingest(tech,'backup','Backup','Keep backups for 14 days.')
    service.ingest(tech,'backup','Backup','Keep backups for 30 days.')
    assert '14 days' in service.read_version(tech,'backup',1).text
    assert '30 days' in service.search(tech,'backups')[0]['quote']
    assert service.search(Actor('x','atlas','technician',frozenset()),'backups') == []
    assert service.search(Actor('b','birch','technician'),'backups') == []
    service.delete(manager,'backup')
    assert service.search(tech,'backups') == []
    with pytest.raises(DomainError):service.read_version(tech,'backup',1)
    restored=service.ingest(tech,'backup','Backup','Keep backups for 90 days.')
    assert restored.version == 3
    assert service.read_version(tech,'backup',1).text == 'Keep backups for 14 days.'


def test_conflicts_expiry_and_page_provenance():
    service=Service(MemoryRepository());tech=Actor('t','atlas','technician')
    for identifier,days in [('a',14),('b',30)]:
        text=f'Backup retention is {days} days.'
        service.ingest(tech,identifier,identifier,text,pages=(Page(2,text),),family='retention',effective='2026-01-01',expires='2026-12-31')
    result=service.search(tech,'backup retention',date(2026,10,8))
    assert len(result)==2 and all(r['status']=='conflicting' and r['page']==2 for r in result)
    assert all(r['status']=='expired' for r in service.search(tech,'retention',date(2027,1,1)))
    assert service.search(tech,'monthly service fee') == []


def test_metadata_change_invalidates_approval():
    service=Service(MemoryRepository());tech=Actor('t','atlas','technician');manager=Actor('m','atlas','service_manager')
    service.ingest(tech,'x','X','Check backup status.',expires='2026-12-31')
    draft=service.prepare(tech,['x'],['Check backup status.'])
    service.ingest(tech,'x','X','Check backup status.',expires='2027-12-31')
    with pytest.raises(DomainError) as error: service.approve(manager,draft.id,draft.payload_hash)
    assert error.value.code == 'source_changed_or_expired'


def test_checklist_has_page_offsets_and_rejects_expired_or_poor_sources():
    service=Service(MemoryRepository());tech=Actor('t','atlas','technician')
    service.ingest(tech,'x','X','Check backup status.',pages=(Page(3,'Check backup status.'),))
    draft=service.prepare(tech,['x'],['Check backup status.'])
    assert draft.step_sources == (('x',1,3,0,20),)
    service.ingest(tech,'expired','Old','Do old thing.',expires='2000-01-01')
    with pytest.raises(DomainError):service.prepare(tech,['expired'],['Do old thing.'])
    service.ingest(tech,'poor','Poor','Unreadable text.',pages=(Page(1,'Unreadable text.','tesseract','review'),))
    with pytest.raises(DomainError):service.prepare(tech,['poor'],['Unreadable text.'])


def test_pdf_upload_api_and_cross_tenant_search():
    from fastapi.testclient import TestClient
    from backend.api import create_app
    token='test-native-api-token-0123456789';other='test-other-token-0123456789'
    client=TestClient(create_app({token:Actor('t','atlas','technician'),other:Actor('b','birch','technician')}))
    body=(ROOT/'evaluation/development/atlas-sla-v1.pdf').read_bytes()
    response=client.post('/pdf-documents?identifier=sla&title=SLA',content=body,headers={'Authorization':'Bearer '+token,'Content-Type':'application/pdf'})
    assert response.status_code == 201,response.text
    assert response.json()['pages'][1]['number']==2
    response=client.get('/search?q=critical+response',headers={'Authorization':'Bearer '+token})
    assert response.status_code==200 and response.json()[0]['page']==2
    assert client.get('/search?q=critical+response',headers={'Authorization':'Bearer '+other}).json()==[]


def test_new_conflicting_source_invalidates_existing_proposal():
    service=Service(MemoryRepository());tech=Actor('t','atlas','technician');manager=Actor('m','atlas','service_manager')
    service.ingest(tech,'a','A','Keep backups for 14 days.',family='retention')
    proposal=service.prepare(tech,['a'],['Keep backups for 14 days.'])
    service.ingest(tech,'b','B','Keep backups for 30 days.',family='retention')
    assert service.read_proposal(manager,proposal.id).status=='stale'
    with pytest.raises(DomainError):service.approve(manager,proposal.id,proposal.payload_hash)


def test_stale_source_view_cannot_prepare_against_unseen_version():
    service=Service(MemoryRepository());actor=Actor('t','atlas','technician')
    service.ingest(actor,'x','X','Check backup status.')
    service.ingest(actor,'x','X','Check backup status. Escalate failures.')
    with pytest.raises(DomainError) as error:
        service.prepare(actor,['x'],['Check backup status.'],{'x':1})
    assert error.value.code=='source_changed_or_expired'


def test_parser_busy_and_real_process_timeout():
    from backend.pdf_parser import _slot
    data=(ROOT/'evaluation/development/atlas-sla-v1.pdf').read_bytes()
    _slot.acquire()
    try:
        with pytest.raises(ParseError) as error:parse_pdf(data)
        assert error.value.code=='parser_busy'
    finally:_slot.release()
    with pytest.raises(ParseError) as error:parse_pdf(data,timeout=.001)
    assert error.value.code=='parse_timeout'
