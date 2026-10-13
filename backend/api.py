"""Local fixture API. Tokens/actors are server-owned; no public default credentials."""
from dataclasses import asdict
import hashlib
from typing import Annotated

from fastapi import Depends, FastAPI, Header, Request, Query
from datetime import date
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from backend.domain import Actor, DomainError, MemoryRepository, Service
from backend.skills import BusinessSkills, PrepareChecklist, AuditReadiness
from backend.assistant_contracts import Question, Extraction
from pathlib import Path
from threading import Lock
import json


class StrictBody(BaseModel):
    model_config = ConfigDict(extra='forbid')


class IngestBody(StrictBody):
    id: str = Field(min_length=1, max_length=100, pattern=r'^[a-zA-Z0-9_-]+$')
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=200_000)


class PrepareBody(StrictBody):
    document_ids: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(min_length=1, max_length=10)
    steps: list[Annotated[str, Field(min_length=1, max_length=2000)]] = Field(min_length=1, max_length=30)
    expected_versions: dict[str,Annotated[int,Field(ge=1)]] | None = Field(default=None,max_length=10)


class ApproveBody(StrictBody):
    payload_hash: str = Field(pattern=r'^[0-9a-f]{64}$')


class SavePreviewBody(StrictBody):
    proposal_id: str = Field(min_length=1,max_length=100)


class AccessBody(StrictBody):
    actor_id: str = Field(min_length=1,max_length=100)
    revoked: bool


def create_app(tokens: dict[str, Actor], repository=None):
    token_actors = {hashlib.sha256(token.encode()).hexdigest(): actor for token, actor in tokens.items()}
    if any(len(token) < 24 for token in tokens):
        raise ValueError('Use high-entropy tokens of at least 24 characters')
    service = Service(repository if repository is not None else MemoryRepository())
    persistence = 'postgres-lab' if repository is not None else 'memory-harness'
    app = FastAPI(title='Private document assistant - ' + persistence, docs_url=None, redoc_url=None)
    app.state.service = service
    app.state.semantic = None
    semantic_lock = Lock()
    skills = BusinessSkills(service, Path(__file__).resolve().parents[1] / 'local/offline-bundle')
    app.state.skills = skills
    app.state.save_ops = None

    def save_ops():
        if app.state.save_ops is None:
            raise DomainError('save_coordinator_unavailable',503)
        return app.state.save_ops

    def operation_view(op):
        return {'id':op.id,'tenant':op.tenant,'proposal_id':op.proposal_id,
                'requested_by':op.requested_by.id,
                'approved_by':op.approved_by.id if op.approved_by else None,
                'payload':json.loads(op.payload_json),'payload_hash':op.payload_hash,
                'expires_at':op.expires_at.isoformat(),'status':op.status,
                'attempts':op.attempts,'external_id':op.external_id,'error':op.error,
                'external_work_completed':False}

    @app.middleware('http')
    async def response_boundaries(request, call_next):
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        return response

    @app.exception_handler(DomainError)
    async def domain_error(_, error):
        return JSONResponse({'error': error.code}, status_code=error.status)

    # Validation errors must not echo document contents, tokens or user payloads.
    from fastapi.exceptions import RequestValidationError
    @app.exception_handler(RequestValidationError)
    async def invalid_request(_, error):
        return JSONResponse({'error': 'invalid_input'}, status_code=422)

    def identity(authorization: str | None = Header(default=None)):
        if not authorization or not authorization.startswith('Bearer '):
            raise DomainError('unauthenticated', 401)
        actor = token_actors.get(hashlib.sha256(authorization[7:].encode()).hexdigest())
        if actor is None:
            raise DomainError('unauthenticated', 401)
        return actor

    Auth = Annotated[Actor, Depends(identity)]

    @app.get('/health')
    def health():
        return {'status': 'ok', 'persistence': persistence, 'offline_validated': False}

    @app.get('/me')
    def me(actor: Auth):
        return {'id': actor.id, 'tenant': actor.tenant, 'role': actor.role}

    @app.get('/runtime-metrics')
    def runtime_metrics(actor: Auth):
        if actor.role != 'administrator':
            raise DomainError('forbidden')
        generator = skills.assistant.generator
        return {'inference_queue_wait_seconds': list(getattr(generator, 'queue_wait_observations', [])),
                'inference_queue_capacity': 10 if getattr(generator, 'queue_wait_seconds', 0) else 0}

    @app.get('/documents')
    def documents(actor: Auth):
        return [{k: v for k, v in asdict(d).items() if k not in {'text','pages'}} for d in service.list_documents(actor)]

    @app.get('/source-reviews')
    def source_reviews(actor: Auth):
        from backend.retrieval import document_status
        visible=service.list_documents(actor)
        today=date.today()
        queue=[]
        for document in visible:
            state=document_status(document,visible,today)
            reasons=([state] if state!='active' else [])
            if any(page.quality!='usable' for page in document.pages):reasons.append('poor_ocr')
            if reasons:queue.append({'document_id':document.id,'version':document.version,'reasons':reasons,'available':True})
        state=getattr(app.state,'worker_state',None)
        owner=getattr(app.state,'worker_identity',None)
        if state and owner and actor.tenant==owner[0] and actor.role in service.READ_ROLES:
            visible_ids={document.id for document in visible}
            for identifier,entry in state['entries'].items():
                if entry.get('status')!='review' or identifier in visible_ids and any(row['document_id']==identifier for row in queue):
                    continue
                if ((actor.document_ids is not None and identifier not in actor.document_ids) or
                    service.repo.is_revoked(actor.tenant,actor.id,identifier)):
                    continue
                queue.append({'document_id':identifier,'version':entry.get('version'),
                              'reasons':[entry.get('error') or 'worker_review'],'available':identifier in visible_ids})
        return queue

    @app.get('/search')
    def search(actor: Auth, q: str = Query(min_length=1,max_length=1000), as_of: date | None = None):
        return service.search(actor, q, as_of)

    @app.get('/semantic-search')
    def semantic_search(actor: Auth, q: str = Query(min_length=1,max_length=1000), as_of: date | None = None):
        from backend.embeddings import LocalEmbeddings
        from backend.native_retrieval import NativeVectorIndex
        # Check the actor before loading the model. The model is process-local
        # and is initialized once after the native RAM preflight.
        if not service.list_documents(actor):
            return []
        if app.state.semantic is None:
            with semantic_lock:
                if app.state.semantic is None:
                    root=Path(__file__).resolve().parents[1]
                    profile=json.loads((root/'config/embedding-profile.json').read_text(encoding='utf-8-sig'))
                    try:
                        encoder=LocalEmbeddings(root/'local/models/multilingual-minilm',profile)
                    except (RuntimeError,FileNotFoundError,ValueError) as error:
                        raise DomainError('embedding_unavailable',503) from error
                    app.state.semantic=NativeVectorIndex(encoder,profile['revision'])
        try:
            return app.state.semantic.search(service,actor,q,as_of)
        except RuntimeError as error:
            raise DomainError('embedding_unavailable',503) from error

    @app.post('/documents/{identifier}/access',status_code=204)
    def access(identifier: str, body: AccessBody, actor: Auth):
        if actor.role != 'administrator':
            raise DomainError('forbidden')
        target=next((a for a in token_actors.values() if a.id==body.actor_id and a.tenant==actor.tenant),None)
        if target is None:
            raise DomainError('actor_not_found',404)
        service.change_access(actor,target,identifier,body.revoked)

    @app.get('/documents/{identifier}/versions/{version}')
    def version(identifier: str, version: int, actor: Auth):
        return asdict(service.read_version(actor, identifier, version))

    @app.delete('/documents/{identifier}', status_code=204)
    def delete(identifier: str, actor: Auth):
        service.delete(actor, identifier)

    @app.post('/pdf-documents', status_code=201)
    async def pdf_ingest(request: Request, actor: Auth,
                         identifier: str = Query(pattern=r'^[a-zA-Z0-9_-]{1,100}$'),
                         title: str = Query(min_length=1,max_length=200),
                         language: str = Query(default='eng',pattern=r'^(eng|ind)$'),
                         family: str | None = Query(default=None,pattern=r'^[a-zA-Z0-9_-]{1,100}$'),
                         effective: date | None = None, expires: date | None = None):
        from backend.pdf_parser import MAX_BYTES, ParseError, parse_pdf
        from starlette.concurrency import run_in_threadpool
        if actor.role not in service.READ_ROLES or (actor.document_ids is not None and identifier not in actor.document_ids):
            raise DomainError('forbidden')
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > MAX_BYTES:
                raise DomainError('file_too_large', 413)
        try:
            parsed = await run_in_threadpool(parse_pdf, bytes(data), language)
        except ParseError as error:
            raise DomainError(error.code, 503 if error.code == 'parser_busy' else 422) from None
        return asdict(service.ingest(actor, identifier, title, '\n\n'.join(p.text for p in parsed.pages),
                                     pages=parsed.pages, source_hash=parsed.sha256,
                                     effective=effective.isoformat() if effective else None,
                                     expires=expires.isoformat() if expires else None,
                                     family=family))

    @app.get('/documents/{identifier}')
    def document(identifier: str, actor: Auth):
        return asdict(service.read_document(actor, identifier))

    @app.post('/documents', status_code=201)
    def ingest(body: IngestBody, actor: Auth):
        return asdict(service.ingest(actor, body.id, body.title, body.text))

    @app.post('/checklists', status_code=201)
    def prepare(body: PrepareBody, actor: Auth):
        if body.expected_versions is None:  # Original manual API contract.
            return asdict(service.prepare(actor, body.document_ids, body.steps))
        return asdict(skills.prepare_service_checklist(actor, PrepareChecklist(
            document_ids=body.document_ids, steps=body.steps, expected_versions=body.expected_versions)))

    @app.post('/skills/prepare_service_checklist', status_code=201)
    def prepare_skill(body: PrepareChecklist, actor: Auth):
        return asdict(skills.prepare_service_checklist(actor, body))

    @app.post('/skills/audit_offline_readiness')
    def readiness_skill(body: AuditReadiness, actor: Auth):
        return skills.audit_offline_readiness(actor, body).model_dump()

    @app.post('/skills/answer_client_question')
    def answer_skill(body: Question, actor: Auth):
        return skills.answer_client_question(actor, body).model_dump()

    @app.post('/skills/extract_service_terms')
    def extract_skill(body: Extraction, actor: Auth):
        return skills.extract_service_terms(actor, body).model_dump()

    @app.get('/checklists')
    def checklists(actor: Auth):
        return [asdict(p) for p in service.list_proposals(actor)]

    @app.get('/checklists/{identifier}')
    def checklist(identifier: str, actor: Auth):
        return asdict(service.read_proposal(actor, identifier))

    @app.post('/checklists/{identifier}/approve')
    def approve(identifier: str, body: ApproveBody, actor: Auth):
        return asdict(service.approve(actor, identifier, body.payload_hash))

    @app.post('/save-operations/prepare',status_code=201)
    def save_prepare(body: SavePreviewBody, actor: Auth):
        return operation_view(save_ops().prepare(actor,body.proposal_id))

    @app.get('/save-operations/{identifier}')
    def save_read(identifier: str, actor: Auth):
        return operation_view(save_ops().read(actor,identifier))

    @app.post('/save-operations/{identifier}/approve')
    def save_approve(identifier: str, body: ApproveBody, actor: Auth):
        return operation_view(save_ops().approve(actor,identifier,body.payload_hash))

    @app.post('/save-operations/{identifier}/dispatch')
    def save_dispatch(identifier: str, actor: Auth):
        return operation_view(save_ops().save(actor,identifier))

    @app.post('/save-operations/{identifier}/verify')
    def save_verify(identifier: str, actor: Auth):
        return operation_view(save_ops().reconcile(actor,identifier))

    @app.get('/audit')
    def audit(actor: Auth):
        return service.audit(actor)

    from fastapi.staticfiles import StaticFiles
    ui = Path(__file__).resolve().parents[1] / 'frontend/dist'
    if ui.is_dir():
        app.mount('/ui', StaticFiles(directory=ui, html=True), name='ui')
    return app
