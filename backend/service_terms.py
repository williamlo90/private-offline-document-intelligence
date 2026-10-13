"""Source-bound service-term contract; no LLM or legal interpretation here."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from backend.domain import DomainError


class Evidence(BaseModel):
    model_config=ConfigDict(extra='forbid')
    document_id:str
    version:int=Field(ge=1)
    page:int=Field(ge=1)
    start:int=Field(ge=0)
    end:int=Field(gt=0)
    quote:str=Field(min_length=1,max_length=5000)


class ServiceTerm(BaseModel):
    model_config=ConfigDict(extra='forbid')
    kind:Literal['coverage','exclusion','procedure','obligation','sla']
    value:str=Field(min_length=1,max_length=2000)
    evidence:Evidence


def validate_term(service,actor,term:ServiceTerm):
    """Extractive contract: value and quoted span must exist exactly in a readable source."""
    ref=term.evidence
    with service.repo.lock:
        document=service.read_version(actor,ref.document_id,ref.version)
        page=next((p for p in document.pages if p.number==ref.page),None)
        if page is None or page.quality!='usable' or ref.end<=ref.start:
            raise DomainError('invalid_evidence',422)
        if page.text[ref.start:ref.end]!=ref.quote or term.value not in ref.quote:
            raise DomainError('unsupported_term',422)
        return term
