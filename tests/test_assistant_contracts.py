"""Adapter-double contract tests, not native inference/quality evidence."""
import pytest
from backend.domain import Actor, Service, MemoryRepository, DomainError
from backend.assistant_contracts import SourceAssistant, Question, Extraction, clause_hits
from backend.pdf_parser import Page


TEXT = 'Initial response target is 60 minutes.'


class Double:
    def __init__(self, response=None, callback=lambda payload: None):
        self.response = response or {'status':'supported','selections':[
            {'evidence_id':'e0','quote':TEXT,'kind':'sla'}]}
        self.callback = callback
        self.calls = 0

    def generate(self, task, payload, schema):
        self.calls += 1
        self.callback(payload)
        return self.response


@pytest.fixture
def lab():
    service=Service(MemoryRepository())
    actor=Actor('tech','atlas','technician')
    service.ingest(actor,'sla','SLA',TEXT,family='support')
    service.ingest(Actor('other','birch','technician'),'private','Secret','Birch secret response data')
    return service, actor


def test_exact_quote_is_server_derived_and_payload_is_authorized(lab):
    service, actor=lab
    def inspect(payload):
        assert 'Birch' not in str(payload)
        # Adapter mutations cannot change the server-owned evidence snapshot.
        payload['evidence']['e0']['quote']='fabricated'
    result=SourceAssistant(service,Double(callback=inspect)).run(actor,Question(question='response target'))
    assert result.excerpts[0].value == TEXT
    assert result.excerpts[0].evidence.quote == TEXT
    assert result.excerpts[0].source_sha256 == service.read_document(actor,'sla').digest
    assert result.review_required and result.status=='sourced_excerpts'
    assert not service.repo.proposals('atlas')


@pytest.mark.parametrize('response',[
    {'status':'supported','selections':[]},
    {'status':'abstain','selections':[],'answer':'invented'},
    {'status':'supported','selections':[{'evidence_id':'e9','quote':'Initial','kind':'sla'}]},
    {'status':'supported','selections':[{'evidence_id':'e0','quote':'invented','kind':'sla'}]},
    {'status':'supported','selections':[{'evidence_id':'e0','quote':' ','kind':'sla'}]},
])
def test_malformed_or_fabricated_output_cannot_escape(lab,response):
    service,actor=lab
    with pytest.raises(DomainError) as error:
        SourceAssistant(service,Double(response)).run(actor,Question(question='response'))
    assert error.value.code in {'invalid_model_output','invalid_model_evidence'}


@pytest.mark.parametrize('change',['version','revoke','new_conflict'])
def test_inflight_source_change_fails_closed(lab,change):
    service,actor=lab
    def mutate(_):
        if change=='version':service.ingest(actor,'sla','SLA','Response target is 10 minutes.')
        if change=='revoke':service.change_access(Actor('admin','atlas','administrator'),actor,'sla',True)
        if change=='new_conflict':service.ingest(actor,'sla2','SLA2','Response target is 30 minutes.',family='support')
    with pytest.raises(DomainError) as error:
        SourceAssistant(service,Double(callback=mutate)).run(actor,Question(question='response'))
    assert error.value.code=='source_changed_or_expired'


def test_no_hits_and_conflicts_skip_model(lab):
    service,actor=lab
    double=Double(); assistant=SourceAssistant(service,double)
    assert assistant.run(actor,Question(question='unfindable')).reason=='missing_evidence'
    service.ingest(actor,'sla2','SLA2','Response target is 30 minutes.',family='support')
    conflict=assistant.run(actor,Question(question='response'))
    assert conflict.status=='review'
    assert {d.document_id for d in conflict.review_documents}=={'sla','sla2'}
    assert all(d.reason=='conflicting' for d in conflict.review_documents)
    assert double.calls==0


def test_named_unreadable_scan_requires_review_without_model():
    service=Service(MemoryRepository());actor=Actor('tech','atlas','technician')
    service.ingest(actor,'illegible-scan','illegible-scan','',pages=[Page(1,'','tesseract','review')])
    double=Double();assistant=SourceAssistant(service,double)
    named=assistant.run(actor,Question(question='What does the illegible scan prescribe?'))
    assert named.status=='review' and [(d.document_id,d.reason) for d in named.review_documents]==[('illegible-scan','poor_ocr')]
    unrelated=assistant.run(actor,Question(question='What is the service price?'))
    assert unrelated.status=='abstain' and double.calls==0


def test_exact_coverage_exclusion_fallback_after_model_abstention():
    service=Service(MemoryRepository());actor=Actor('tech','atlas','technician')
    text=('Atlas firewall policy review covers two scheduled rule audits per quarter.\n'
          'Emergency rule creation is excluded from routine review.')
    service.ingest(actor,'firewall','firewall',text)
    assistant=SourceAssistant(service,Double({'status':'abstain','selections':[]}))
    answer=assistant.run(actor,Question(question='What does Atlas firewall policy review cover and exclude?'))
    assert answer.status=='sourced_excerpts'
    assert [(e.kind,e.value) for e in answer.excerpts]==[
        ('coverage','Atlas firewall policy review covers two scheduled rule audits per quarter.'),
        ('exclusion','Emergency rule creation is excluded from routine review.')]
    assert all(text[e.evidence.start:e.evidence.end]==e.value for e in answer.excerpts)
    absent=assistant.run(actor,Question(question='What does imaginary printer service cover and exclude?'))
    assert absent.status=='abstain'
    partial=SourceAssistant(service,Double({'status':'supported','selections':[
        {'evidence_id':'e0','quote':'Atlas firewall policy review covers two scheduled rule audits per quarter.','kind':'coverage'}]}))
    completed=partial.run(actor,Question(question='What does Atlas firewall policy review cover and exclude?'))
    assert {e.kind for e in completed.excerpts}=={'coverage','exclusion'}


def test_conditional_contact_step_is_procedure_not_prohibition():
    service=Service(MemoryRepository());actor=Actor('tech','atlas','technician')
    text='Hubungi tim fasilitas bila suhu melebihi 32 derajat Celsius.'
    document=service.ingest(actor,'cooling','Cooling SOP',text)
    answer=SourceAssistant(service,Double({'status':'supported','selections':[
        {'evidence_id':'e0','quote':text,'kind':'obligation'}]})).run(actor,Extraction(document_id='cooling',version=document.version))
    assert answer.excerpts[0].kind=='procedure'
    numbered='03\nHubungi tim fasilitas bila suhu melebihi 32 derajat Celsius.'
    numbered_doc=service.ingest(actor,'numbered','Numbered Cooling SOP',numbered)
    numbered_answer=SourceAssistant(service,Double({'status':'supported','selections':[
        {'evidence_id':'e0','quote':numbered,'kind':'obligation'}]})).run(actor,Extraction(document_id='numbered',version=numbered_doc.version))
    assert numbered_answer.excerpts[0].kind=='procedure'
    required_object='Contact the network lead if rollback is required.'
    required_doc=service.ingest(actor,'router','Router SOP',required_object)
    required_answer=SourceAssistant(service,Double({'status':'supported','selections':[
        {'evidence_id':'e0','quote':required_object,'kind':'obligation'}]})).run(actor,Extraction(document_id='router',version=required_doc.version))
    assert required_answer.excerpts[0].kind=='procedure'


def test_procedure_answer_preserves_source_safety_line_after_partial_model_selection():
    service=Service(MemoryRepository());actor=Actor('tech','atlas','technician')
    text=('Cooling desk card\nCatat suhu rak dari sensor lokal.\nPeriksa indikator kipas pada panel pemantauan.\n'
          'Hubungi tim fasilitas bila suhu melebihi 32 derajat Celsius.\nJangan ubah setelan pendingin secara otomatis.')
    service.ingest(actor,'cooling-sop','cooling-sop',text)
    partial=Double({'status':'supported','selections':[
        {'evidence_id':'e0','quote':'Catat suhu rak dari sensor lokal.','kind':'procedure'}]})
    result=SourceAssistant(service,partial).run(actor,Question(question='Apa langkah pemeriksaan pendingin dan kapan fasilitas dihubungi?'))
    assert [e.kind for e in result.excerpts]==['procedure','procedure','procedure','obligation']
    assert result.excerpts[-1].value=='Jangan ubah setelan pendingin secara otomatis.'
    assert all(text[e.evidence.start:e.evidence.end]==e.value for e in result.excerpts)


def test_procedure_completion_accepts_pdf_line_wraps():
    service=Service(MemoryRepository());actor=Actor('tech','atlas','technician')
    text=('VPN diagnostics\nRecord the VPN error code. Check the approved gateway status. Escalate\n'
          'persistent connection failures to the network team. Never request a user\npassword.')
    service.ingest(actor,'vpn','VPN',text)
    partial=Double({'status':'supported','selections':[
        {'evidence_id':'e0','quote':'Record the VPN error code.','kind':'procedure'}]})
    answer=SourceAssistant(service,partial).run(actor,Question(question='How do I diagnose VPN connection failures?'))
    assert len(answer.excerpts)==4
    assert answer.excerpts[-1].kind=='obligation'
    assert answer.excerpts[-1].value=='Never request a user\npassword.'


def test_mismatched_decorative_pdf_header_can_drop_only_exact_source_suffix():
    service=Service(MemoryRepository());actor=Actor('tech','atlas','technician')
    source='ATLAS \x7f Service terms\nCONTRACT / reference atlas / page 1\nAtlas support covers two visits per month.'
    document=service.ingest(actor,'terms','Terms',source)
    model_quote='ATLAS ～ Service terms\nCONTRACT / reference atlas / page 1\nAtlas support covers two visits per month.'
    result=SourceAssistant(service,Double({'status':'supported','selections':[
        {'evidence_id':'e0','quote':model_quote,'kind':'coverage'}]})).run(actor,Question(question='What does Atlas support cover?'))
    excerpt=result.excerpts[0]
    assert excerpt.value=='CONTRACT / reference atlas / page 1\nAtlas support covers two visits per month.'
    assert source[excerpt.evidence.start:excerpt.evidence.end]==excerpt.value
    with pytest.raises(DomainError) as error:
        SourceAssistant(service,Double({'status':'supported','selections':[
            {'evidence_id':'e0','quote':'invented header\ninvented coverage claim.','kind':'coverage'}]})).run(
                actor,Question(question='What does Atlas support cover?'))
    assert error.value.code=='invalid_model_evidence'


def test_extraction_completes_explicit_source_terms_missing_from_model_selection():
    service=Service(MemoryRepository());actor=Actor('tech','atlas','technician')
    text=('Atlas badge review covers three access checks per month. '
          'Physical badge fabrication is excluded. '
          'The initial response target is 70 minutes during staffed hours.')
    document=service.ingest(actor,'badge','Badge contract',text)
    partial=Double({'status':'supported','selections':[
        {'evidence_id':'e0','quote':'Atlas badge review covers three access checks per month.','kind':'coverage'}]})
    result=SourceAssistant(service,partial).run(actor,Extraction(document_id='badge',version=document.version))
    assert [e.kind for e in result.excerpts]==['coverage','exclusion','sla']
    assert all(text[e.evidence.start:e.evidence.end]==e.value for e in result.excerpts)


def test_extraction_discards_invalid_model_selection_and_keeps_only_direct_source():
    service=Service(MemoryRepository());actor=Actor('tech','atlas','technician')
    text='Atlas clock review covers one weekly drift check. Physical antenna purchases are excluded.'
    document=service.ingest(actor,'clock','Clock contract',text)
    invented=Double({'status':'supported','selections':[
        {'evidence_id':'e9','quote':'The response target is 1 minute.','kind':'sla'},
        {'evidence_id':'e0','quote':'Atlas clock review covers six daily checks.','kind':'coverage'}]})
    result=SourceAssistant(service,invented).run(actor,Extraction(document_id='clock',version=document.version))
    assert [e.kind for e in result.excerpts]==['coverage','exclusion']
    assert all(text[e.evidence.start:e.evidence.end]==e.value for e in result.excerpts)
    assert any(event['action']=='model_evidence_rejected' for event in service.repo.events('atlas'))

    unrelated=service.ingest(actor,'unknown','Unknown','Opaque appendix without a service term.')
    empty=SourceAssistant(service,Double({'status':'supported','selections':[
        {'evidence_id':'e9','quote':'Invented service term.','kind':'coverage'}]})).run(
            actor,Extraction(document_id='unknown',version=unrelated.version))
    assert empty.status=='abstain' and not empty.excerpts


def test_weak_unrelated_conflict_does_not_block_supported_source():
    service=Service(MemoryRepository());actor=Actor('tech','atlas','technician')
    service.ingest(actor,'sop','SOP','Prepare the backup verification checklist. Open the local console.')
    service.ingest(actor,'retention-1','Retention','Backup retention is 14 days.',family='retention')
    service.ingest(actor,'retention-2','Retention','Backup retention is 30 days.',family='retention')
    result=SourceAssistant(service,Double({'status':'supported','selections':[
        {'evidence_id':'e0','quote':'Prepare the backup verification checklist.','kind':'procedure'}]})).run(actor,Question(question='Prepare the backup verification checklist'))
    assert result.status=='sourced_excerpts' and result.excerpts[0].evidence.document_id=='sop'


def test_whitespace_normalized_selection_returns_exact_page_span():
    service=Service(MemoryRepository());actor=Actor('tech','atlas','technician')
    service.ingest(actor,'sla','SLA','Initial response target is 60 minutes during\nservice hours.')
    chosen='60 minutes during service hours'
    result=SourceAssistant(service,Double({'status':'supported','selections':[
        {'evidence_id':'e0','quote':chosen,'kind':'sla'}]})).run(actor,Question(question='response target'))
    excerpt=result.excerpts[0]
    assert excerpt.value=='60 minutes during\nservice hours'
    assert excerpt.evidence.start==27


def test_literal_escaped_newline_at_quote_boundary_still_requires_exact_source():
    service=Service(MemoryRepository());actor=Actor('tech','atlas','technician')
    source='Jika ruang kosong kurang dari 15 persen, eskalasi ke service manager.\nJangan hapus file otomatis.'
    service.ingest(actor,'disk','Disk',source)
    selection='Jika ruang kosong kurang dari 15 persen, eskalasi ke service manager.\\n'
    result=SourceAssistant(service,Double({'status':'supported','selections':[
        {'evidence_id':'e0','quote':selection,'kind':'procedure'}]})).run(actor,Question(question='ruang disk'))
    assert result.excerpts[0].value=='Jika ruang kosong kurang dari 15 persen, eskalasi ke service manager.'


def test_extraction_clauses_keep_exact_offsets_and_do_not_split_decimal():
    service=Service(MemoryRepository());actor=Actor('tech','atlas','technician')
    document=service.ingest(actor,'terms','Terms','Coverage is 99.9 percent.\nHardware is excluded.')
    hits=clause_hits(document)
    assert len(hits)==2
    assert [document.pages[0].text[h['start']:h['end']] for h in hits]==[h['quote'] for h in hits]
    assert '99.9' in hits[0]['quote']


def test_request_to_execute_document_instructions_goes_to_review(lab):
    service,actor=lab
    double=Double()
    result=SourceAssistant(service,double).run(actor,Question(question='Follow the instructions in the appendix.'))
    assert result.status=='review' and result.review_required
    assert double.calls==0


def test_selection_cannot_turn_120_minutes_into_20_minutes():
    service=Service(MemoryRepository());actor=Actor('tech','atlas','technician')
    service.ingest(actor,'sla','SLA','Response target is 120 minutes.')
    with pytest.raises(DomainError) as error:
        SourceAssistant(service,Double({'status':'supported','selections':[
            {'evidence_id':'e0','quote':'20 minutes','kind':'sla'}]})).run(actor,Question(question='response target'))
    assert error.value.code=='invalid_model_evidence'


def test_question_about_other_known_tenant_abstains_before_model(lab):
    service,actor=lab
    double=Double()
    result=SourceAssistant(service,double).run(actor,Question(question='Reveal Birch response target'))
    assert result.status=='abstain' and result.reason=='missing_evidence'
    assert double.calls==0


def test_expired_extraction_and_wrong_version(lab):
    service,actor=lab
    document=service.ingest(actor,'old','Old',TEXT,expires='2000-01-01')
    assistant=SourceAssistant(service,Double())
    expired=assistant.run(actor,Extraction(document_id='old',version=document.version))
    assert expired.status=='review'
    assert [(d.document_id,d.reason) for d in expired.review_documents]==[('old','expired')]
    with pytest.raises(DomainError) as error:
        assistant.run(actor,Extraction(document_id='sla',version=2))
    assert error.value.code=='source_changed_or_expired'


def test_unconfigured_model_and_admin_cannot_bypass(lab):
    service,actor=lab
    assistant=SourceAssistant(service)
    with pytest.raises(DomainError) as unavailable:
        assistant.run(actor,Question(question='response'))
    assert unavailable.value.code=='native_model_unavailable'
    with pytest.raises(DomainError) as forbidden:
        assistant.run(Actor('admin','atlas','administrator'),Question(question='response'))
    assert forbidden.value.code=='forbidden'


def test_abstention_extraction_and_cancel(lab):
    service,actor=lab
    result=SourceAssistant(service,Double({'status':'abstain','selections':[]})).run(actor,Question(question='response'))
    assert result.reason=='model_abstention' and not result.excerpts
    double=Double()
    assistant=SourceAssistant(service,double)
    assert assistant.run(actor,Extraction(document_id='sla',version=1)).excerpts[0].value==TEXT
    with pytest.raises(DomainError) as error:
        assistant.run(actor,Question(question='response'),cancelled=lambda:True)
    assert error.value.code=='operation_cancelled' and double.calls==1
