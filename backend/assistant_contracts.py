"""Source-selection contracts. No native model is configured by default."""
from datetime import date
from copy import deepcopy
from contextlib import nullcontext
import re
from typing import Literal, Protocol
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from backend.domain import DomainError
from backend.service_terms import Evidence


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Question(Strict):
    question: str = Field(min_length=1, max_length=1000)


class Extraction(Strict):
    document_id: str = Field(min_length=1, max_length=100)
    version: int = Field(ge=1)


class Selection(Strict):
    evidence_id: str = Field(pattern=r'^e[0-9]{1,3}$', description='Identifier of the supplied evidence containing this quote')
    quote: str = Field(min_length=1, max_length=2000, description='Exact relevant sentence or clause copied from that evidence')
    kind: Literal['coverage', 'exclusion', 'procedure', 'obligation', 'sla'] = Field(
        description='coverage=included service or service hours; exclusion=not included; procedure=operational step; '
                    'obligation=required or forbidden action; sla=measured response/availability target')


class Candidate(Strict):
    status: Literal['supported', 'abstain'] = Field(description='supported when evidence answers the task; abstain only when it does not')
    selections: list[Selection] = Field(max_length=30, description='Relevant exact quotes; empty only with abstain')

    @model_validator(mode='after')
    def consistent(self):
        if (self.status == 'supported') != bool(self.selections):
            raise ValueError('status and selections disagree')
        return self


class CitedExcerpt(Strict):
    kind: Literal['coverage', 'exclusion', 'procedure', 'obligation', 'sla']
    value: str
    evidence: Evidence
    source_sha256: str


class ReviewDocument(Strict):
    document_id: str
    version: int
    reason: Literal['expired', 'not_yet_effective', 'poor_ocr', 'conflicting']


class SourceResult(Strict):
    schema_version: Literal['1.0'] = '1.0'
    status: Literal['sourced_excerpts', 'abstain', 'review']
    reason: Literal['source_selection', 'missing_evidence', 'model_abstention', 'source_requires_review', 'context_limit']
    excerpts: list[CitedExcerpt] = Field(default_factory=list)
    review_documents: list[ReviewDocument] = Field(default_factory=list)
    review_required: Literal[True] = True


class LocalGenerator(Protocol):
    def generate(self, task: str, payload: dict, schema: dict) -> dict: ...


def source_issue(document, documents):
    today = date.today().isoformat()
    if document.effective and document.effective > today:
        return 'not_yet_effective'
    if document.expires and document.expires < today:
        return 'expired'
    if any(p.quality != 'usable' for p in document.pages):
        return 'poor_ocr'
    if document.family and any(d.id != document.id and d.family == document.family and d.digest != document.digest
                              and (not d.effective or d.effective <= today) and (not d.expires or d.expires >= today)
                              for d in documents):
        return 'conflicting'
    return None


def source_state(document, documents):
    return 'review' if source_issue(document, documents) else 'active'


def review_documents(documents, visible):
    return [ReviewDocument(document_id=d.id,version=d.version,reason=issue)
            for d in documents if (issue:=source_issue(d, visible))]


def snapshot(documents):
    return {d.id: d for d in documents}


def clause_hits(document):
    """Bound extraction evidence to one source sentence per hit, retaining offsets."""
    hits=[]
    for page in document.pages:
        start=0
        for boundary in re.finditer(r'\.(?=\s|$)', page.text):
            end=boundary.end()
            raw=page.text[start:end]
            left=len(raw)-len(raw.lstrip())
            right=len(raw.rstrip())
            if right>left:
                hits.append({'document_id':document.id,'version':document.version,'page':page.number,
                             'start':start+left,'end':start+right,'quote':raw[left:right]})
            start=end
        raw=page.text[start:]
        left=len(raw)-len(raw.lstrip());right=len(raw.rstrip())
        if right>left:
            hits.append({'document_id':document.id,'version':document.version,'page':page.number,
                         'start':start+left,'end':start+right,'quote':raw[left:right]})
    return hits


def direct_service_kind(quote):
    """Classify direct source clauses; never infer a value absent from the quote."""
    compact=' '.join(quote.split())
    if re.search(r'\b(?:excluded|not included|not covered)\b',compact,re.I):
        return 'exclusion'
    if re.search(r'\b(?:initial response|response target|acknowledgement target|targeted within|resolution guarantee)\b',compact,re.I):
        return 'sla'
    line_start=r'(?:^|\n)\s*(?:\d+\s*[.):]?\s*)?'
    if re.search(line_start+r'(?:never|do not|jangan)\b',quote,re.I):
        return 'obligation'
    if re.search(line_start+r'(?:step\s+\d+:|first,|next,|then\b|record\b|check\b|capture\b|ask\b|open\b|verify\b|contact\b|call\b|escalate\b|catat\b|periksa\b|hubungi\b|buka\b|eskalasi\b)',quote,re.I):
        return 'procedure'
    if re.search(r'\b(?:covers?|operates|available|provides?)\b',compact,re.I):
        return 'coverage'
    return None


class SourceAssistant:
    def __init__(self, service, generator: LocalGenerator | None = None):
        self.service, self.generator = service, generator

    def run(self, actor, request: Question | Extraction, *, cancelled=lambda: False):
        scope = self.service.repo.scoped(actor) if hasattr(self.service.repo, 'scoped') else nullcontext()
        with scope:
            return self._run_scoped(actor, request, cancelled=cancelled)

    def _run_scoped(self, actor, request: Question | Extraction, *, cancelled=lambda: False):
        with self.service.repo.lock:
            documents = self.service.list_documents(actor)
            before = snapshot(documents)
            if isinstance(request, Extraction):
                document = self.service.read_document(actor, request.document_id)
                if document.version != request.version:
                    raise DomainError('source_changed_or_expired', 409)
                hits = clause_hits(document)
                task, question = ('extract_service_terms',
                                  'Extract every coverage, exclusion, procedure, obligation and SLA clause in this document.')
                review_sources = [document]
            else:
                query_tenants={part.casefold() for part in re.findall(r'\b[\w-]+\b',request.question)}
                if any(tenant.casefold() in query_tenants and tenant!=actor.tenant
                       for tenant in self.service.repo.tenant_ids()):
                    return SourceResult(status='abstain',reason='missing_evidence')
                if re.match(r'^\s*(follow|obey|execute)\b.*\binstructions?\b', request.question, re.I):
                    return SourceResult(status='review', reason='source_requires_review')
                hits = self.service.search(actor, request.question)
                task, question = 'answer_client_question', request.question
                # Search can return weak, unrelated hits. A conflicting or expired
                # source blocks the answer when it competes with the best hit;
                # any later selection from such a source also triggers review.
                strongest = hits[0]['score'] if hits else 0
                review_sources = [before[h['document_id']] for h in hits
                                  if h['score'] >= strongest * 0.8]
                # Keep weak keyword matches out of the model context when a
                # substantially stronger source exists. The search endpoint
                # still exposes the full authorized list for human review.
                if strongest >= .4:
                    hits = [h for h in hits if h['score'] >= max(.25, strongest * .5)]
            issues=review_documents(review_sources,documents)
            if issues:
                return SourceResult(status='review', reason='source_requires_review',review_documents=issues)
            if not hits:
                # An unreadable scan has no searchable text. If the question
                # names that source, surface it for review rather than treating
                # its missing OCR as proof that no document exists.
                terms=set(re.findall(r'\w+', question.casefold()))
                named_unreadable=[d for d in documents if any(p.quality != 'usable' for p in d.pages)
                                  and len(terms & set(re.findall(r'\w+', (d.title+' '+d.id).casefold()))) >= 2]
                if named_unreadable:
                    return SourceResult(status='review', reason='source_requires_review',
                                        review_documents=review_documents(named_unreadable, documents))
                return SourceResult(status='abstain', reason='missing_evidence')
            if len(hits) > 100 or sum(len(h['quote']) for h in hits) > 24000:
                return SourceResult(status='review', reason='context_limit')
            evidence = {f'e{i}': dict(h) for i, h in enumerate(hits)}
        if cancelled():
            raise DomainError('operation_cancelled', 409)
        if self.generator is None:
            raise DomainError('native_model_unavailable', 503)
        # Only authorized text enters the adapter. Model output has no actions or
        # free-form claims; it may select exact spans or abstain.
        payload = {'question':question, 'evidence':evidence}
        try:
            candidate = Candidate.model_validate(self.generator.generate(task, deepcopy(payload), Candidate.model_json_schema()))
        except ValidationError:
            raise DomainError('invalid_model_output', 502) from None
        if isinstance(request, Extraction):
            # Direct, explicit source terms take precedence over model output
            # for the same sentence. This avoids treating a model's PDF label
            # or line-number transcription as a factual quote. Other model
            # selections remain subject to strict span validation below.
            direct={}
            for identifier,hit in evidence.items():
                kind=direct_service_kind(hit['quote'])
                if kind and len(hit['quote'].strip())<=2000:
                    direct[identifier]=Selection(evidence_id=identifier,quote=hit['quote'].strip(),kind=kind)
            retained=[selection for selection in candidate.selections if selection.evidence_id not in direct]
            selections=[*retained,*direct.values()]
            if len(selections)>30:
                return SourceResult(status='review',reason='context_limit')
            candidate=Candidate(status='supported' if selections else 'abstain',selections=selections)
        if (isinstance(request, Question)
            and not {'coverage','exclusion'} <= {selection.kind for selection in candidate.selections}):
            # The model can omit one part of a two-part coverage and exclusion
            # question even when both direct source lines are present.
            # A narrow, source-exact fallback handles only that declared task;
            # the normal version/permission/span checks below still apply.
            if (re.search(r'\bcover\w*\b', question, re.I) and re.search(r'\bexclud\w*\b', question, re.I)
                and hits and hits[0]['score'] >= .45
                and (len(hits) == 1 or hits[1]['score'] < hits[0]['score'] * .5)):
                top=hits[0]
                stop={'what','does','the','a','an','and','cover','covers','exclude','excluded','is','are','of','for','service'}
                distinctive=set(re.findall(r'\w+', question.casefold()))-stop
                if len(distinctive & set(re.findall(r'\w+', top['quote'].casefold()))) >= 2:
                    lines=[line.strip() for line in top['quote'].splitlines() if line.strip().endswith('.')]
                    included=next((line for line in lines if re.search(r'\bcover\w*\b',line,re.I)),None)
                    excluded=next((line for line in lines if re.search(r'\bexclud\w*\b',line,re.I)),None)
                    if included and excluded:
                        candidate=Candidate.model_validate({'status':'supported','selections':[
                            {'evidence_id':'e0','quote':included,'kind':'coverage'},
                            {'evidence_id':'e0','quote':excluded,'kind':'exclusion'}]})
        if (isinstance(request, Question) and hits and hits[0]['score'] >= .25
            and (len(hits) == 1 or hits[1]['score'] < hits[0]['score'] * .75)
            and re.search(r'\b(?:steps?|procedure|diagnos\w*|langkah|penanganan|pemeriksaan)\b', question, re.I)):
            # Operational desk cards often state steps as separate sentences.
            # Preserve every direct action and safety prohibition on the best
            # authorized page; a model may omit a safety line in a long list.
            actions=[]
            action_start=r'\b(?:Step\s+\d+:|First,|Next,|Then\b|Record\b|Check\b|Capture\b|Ask\b|Open\b|Verify\b|Contact\b|Escalate\b|Catat\b|Periksa\b|Hubungi\b|Jangan\b|Never\b|Do not\b)'
            normalized_page=re.sub(r'\s+',' ',hits[0]['quote'])
            for part in re.split(r'(?<=[.!?])\s+', normalized_page):
                match=re.search(action_start,part,re.I)
                sentence=part[match.start():].strip() if match else ''
                if sentence.endswith('.'):
                    kind='obligation' if re.match(r'^(?:Jangan|Never|Do not)\b',sentence,re.I) else 'procedure'
                    actions.append({'evidence_id':'e0','quote':sentence,'kind':kind})
            if len(actions) >= 2:
                candidate=Candidate.model_validate({'status':'supported','selections':actions})
        if cancelled():
            raise DomainError('operation_cancelled', 409)
        with self.service.repo.lock:
            current = self.service.list_documents(actor)
            if snapshot(current) != before:
                raise DomainError('source_changed_or_expired', 409)
            excerpts = []
            rejected_extraction_selections=0
            for selection in candidate.selections:
                hit = evidence.get(selection.evidence_id)
                if hit is None or not selection.quote.strip():
                    if task == 'extract_service_terms':
                        rejected_extraction_selections+=1
                        continue
                    raise DomainError('invalid_model_evidence', 502)
                if source_state(before[hit['document_id']], current) != 'active':
                    return SourceResult(status='review', reason='source_requires_review',
                                        review_documents=review_documents([before[hit['document_id']]],current))
                # Some JSON-schema model outputs contain a literal escaped line
                # break at a quote boundary. It carries no fact; the final value
                # still comes only from an exact match in the source page.
                quote = re.sub(r'^(?:\\[nr])+|(?:\\[nr])+$', '', selection.quote.strip()).strip()
                pattern = r'\s+'.join(re.escape(part) for part in quote.split())
                if pattern and quote[0].isalnum():
                    pattern=r'(?<!\w)'+pattern
                if pattern and quote[-1].isalnum():
                    pattern=pattern+r'(?!\w)'
                matches=list(re.finditer(pattern, hit['quote'])) if pattern else []
                if len(matches) != 1 and '\n' in quote:
                    # A PDF heading may contain a glyph the model normalizes
                    # differently (for example a decorative separator). Only
                    # drop leading lines; the retained factual suffix must be
                    # a unique, exact source span of meaningful length.
                    lines=quote.splitlines()
                    for index in range(1,len(lines)):
                        suffix='\n'.join(lines[index:]).strip()
                        if len(suffix)<25 or len(suffix.split())<4:
                            continue
                        suffix_pattern=r'\s+'.join(re.escape(part) for part in suffix.split())
                        if suffix[0].isalnum():suffix_pattern=r'(?<!\w)'+suffix_pattern
                        if suffix[-1].isalnum():suffix_pattern+=r'(?!\w)'
                        suffix_matches=list(re.finditer(suffix_pattern,hit['quote']))
                        if len(suffix_matches)==1:
                            matches=suffix_matches
                            break
                if len(matches) != 1:
                    if task == 'extract_service_terms':
                        rejected_extraction_selections+=1
                        continue
                    raise DomainError('invalid_model_evidence', 502)
                start, end = matches[0].span()
                value = hit['quote'][start:end]
                ref = Evidence(document_id=hit['document_id'], version=hit['version'], page=hit['page'],
                               start=hit['start']+start, end=hit['start']+end, quote=value)
                kind=selection.kind
                if task == 'extract_service_terms':
                    direct=direct_service_kind(value)
                    if direct:kind=direct
                    clause=re.sub(r'^\s*(?:\d+\s*[.):]?\s*)?', '', value)
                    if re.match(r'^(?:never|do not|jangan)\b',clause,re.I):
                        kind='obligation'
                    elif (re.match(r'^(?:step\s+\d+:|first,|next,|then\b|record\b|check\b|capture\b|ask\b|open\b|verify\b|contact\b|call\b|escalate\b|catat\b|periksa\b|hubungi\b|buka\b|eskalasi\b)',clause,re.I)
                          and not re.search(r'\b(?:must|wajib)\b', clause,re.I)):
                        kind='procedure'
                excerpts.append(CitedExcerpt(kind=kind, value=value, evidence=ref,
                                             source_sha256=before[hit['document_id']].digest))
            result = SourceResult(status='sourced_excerpts' if excerpts else 'abstain',
                                  reason='source_selection' if excerpts else 'model_abstention', excerpts=excerpts)
            if rejected_extraction_selections:
                self.service.repo.record(actor.tenant, actor.id, 'model_evidence_rejected',
                                         str(rejected_extraction_selections))
            self.service.repo.record(actor.tenant, actor.id, task, result.status)
            return result
