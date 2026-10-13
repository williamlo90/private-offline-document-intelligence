import pytest
from backend.domain import Actor,Service,MemoryRepository,DomainError
from backend.service_terms import ServiceTerm,validate_term


def test_numeric_term_requires_exact_accessible_source():
    service=Service(MemoryRepository());actor=Actor('t','atlas','technician')
    text='Initial response target is 60 minutes.'
    service.ingest(actor,'sla','SLA',text)
    data={'kind':'sla','value':'60 minutes','evidence':{'document_id':'sla','version':1,'page':1,'start':0,'end':len(text),'quote':text}}
    assert validate_term(service,actor,ServiceTerm(**data)).value=='60 minutes'
    with pytest.raises(DomainError):validate_term(service,actor,ServiceTerm(**{**data,'value':'20 minutes'}))
    with pytest.raises(DomainError):validate_term(service,Actor('b','birch','technician'),ServiceTerm(**data))
