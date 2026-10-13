"""Native domain foundation. In-memory persistence is a harness, not production storage."""
from dataclasses import dataclass, replace
from contextlib import nullcontext
from datetime import date, datetime, timedelta, timezone
from functools import wraps
import hashlib
import json
from threading import RLock
from typing import Protocol
from uuid import uuid4
from backend.pdf_parser import Page


class DomainError(Exception):
    def __init__(self, code: str, status: int = 403):
        self.code, self.status = code, status


@dataclass(frozen=True)
class Actor:
    id: str
    tenant: str
    role: str
    document_ids: frozenset[str] | None = None


@dataclass(frozen=True)
class Document:
    id: str
    tenant: str
    title: str
    version: int
    text: str
    digest: str
    pages: tuple[Page, ...] = ()
    effective: str | None = None
    expires: str | None = None
    family: str = ''
    deleted: bool = False


@dataclass(frozen=True)
class Proposal:
    id: str
    tenant: str
    actor_id: str
    source_versions: tuple[tuple[str, int, str], ...]
    steps: tuple[str, ...]
    payload_hash: str
    expires_at: datetime
    step_sources: tuple[tuple[str, int, int, int, int], ...] = ()
    status: str = 'review'
    approver_id: str | None = None


class Repository(Protocol):
    lock: RLock
    def documents(self, tenant: str) -> list[Document]: ...
    def tenant_ids(self) -> set[str]: ...
    def document(self, tenant: str, identifier: str) -> Document | None: ...
    def put_document(self, document: Document) -> None: ...
    def document_version(self, tenant: str, identifier: str, version: int) -> Document | None: ...
    def proposal(self, tenant: str, identifier: str) -> Proposal | None: ...
    def put_proposal(self, proposal: Proposal) -> None: ...
    def proposals(self, tenant: str) -> list[Proposal]: ...
    def record(self, tenant: str, actor: str, action: str, resource: str) -> None: ...
    def events(self, tenant: str) -> list[dict]: ...
    def is_revoked(self, tenant: str, actor_id: str, document_id: str) -> bool: ...
    def set_revoked(self, tenant: str, actor_id: str, document_id: str, revoked: bool) -> None: ...


class MemoryRepository:
    """Only intended for fixtures/native contract testing; lost on process exit."""
    def __init__(self):
        self.lock = RLock()
        self._documents: dict[tuple[str, str], Document] = {}
        self._versions: dict[tuple[str, str, int], Document] = {}
        self._proposals: dict[tuple[str, str], Proposal] = {}
        self._events: list[dict] = []
        self._revocations: set[tuple[str,str,str]] = set()

    def is_revoked(self, tenant, actor_id, document_id):
        return (tenant,actor_id,document_id) in self._revocations

    def set_revoked(self, tenant, actor_id, document_id, revoked):
        key=(tenant,actor_id,document_id)
        if revoked:self._revocations.add(key)
        else:self._revocations.discard(key)

    def documents(self, tenant):
        return [d for (t, _), d in self._documents.items() if t == tenant]

    def tenant_ids(self):
        return {tenant for tenant, _ in self._documents}

    def document(self, tenant, identifier):
        return self._documents.get((tenant, identifier))

    def put_document(self, document):
        self._documents[(document.tenant, document.id)] = document
        key = (document.tenant, document.id, document.version)
        if key not in self._versions:
            self._versions[key] = document

    def document_version(self, tenant, identifier, version):
        return self._versions.get((tenant, identifier, version))

    def proposal(self, tenant, identifier):
        return self._proposals.get((tenant, identifier))

    def put_proposal(self, proposal):
        self._proposals[(proposal.tenant, proposal.id)] = proposal

    def proposals(self, tenant):
        return [p for (t, _), p in self._proposals.items() if t == tenant]

    def record(self, tenant, actor, action, resource):
        self._events.append({'tenant': tenant, 'actor': actor, 'action': action, 'resource': resource,
                             'at': datetime.now(timezone.utc).isoformat()})

    def events(self, tenant):
        return [dict(e) for e in self._events if e['tenant'] == tenant]


def repository_scope(method):
    """Bind the authenticated actor before any persistent repository operation."""
    @wraps(method)
    def wrapped(self, actor, *args, **kwargs):
        scope = getattr(self.repo, 'scoped', None)
        with scope(actor) if scope else nullcontext():
            return method(self, actor, *args, **kwargs)
    return wrapped


class Service:
    READ_ROLES = frozenset({'technician', 'service_manager'})

    def __init__(self, repository: Repository):
        self.repo = repository

    def _can_read(self, actor, document):
        return (not document.deleted and actor.role in self.READ_ROLES and actor.tenant == document.tenant
                and not self.repo.is_revoked(actor.tenant,actor.id,document.id)
                and (actor.document_ids is None or document.id in actor.document_ids))

    def _document(self, actor, identifier):
        document = self.repo.document(actor.tenant, identifier)
        if document is None or not self._can_read(actor, document):
            raise DomainError('document_not_found', 404)
        return document

    @repository_scope
    def list_documents(self, actor):
        if actor.role not in self.READ_ROLES:
            raise DomainError('forbidden')
        with self.repo.lock:
            return [d for d in self.repo.documents(actor.tenant) if self._can_read(actor, d)]

    @repository_scope
    def read_document(self, actor, identifier):
        with self.repo.lock:
            result = self._document(actor, identifier)
            self.repo.record(actor.tenant, actor.id, 'document_read', identifier)
            return result

    @repository_scope
    def ingest(self, actor, identifier, title, text, *, pages=None, source_hash=None, effective=None, expires=None, family=''):
        if actor.role not in self.READ_ROLES:
            raise DomainError('forbidden')
        if actor.document_ids is not None and identifier not in actor.document_ids:
            raise DomainError('forbidden')
        try:
            if effective: date.fromisoformat(effective)
            if expires: date.fromisoformat(expires)
            if effective and expires and effective > expires: raise ValueError()
        except ValueError:
            raise DomainError('invalid_dates', 422) from None
        pages = tuple(pages) if pages is not None else (Page(1, text, 'manual'),)
        with self.repo.lock:
            if self.repo.is_revoked(actor.tenant,actor.id,identifier):
                raise DomainError('forbidden')
            old = self.repo.document(actor.tenant, identifier)
            digest = source_hash or hashlib.sha256(text.encode()).hexdigest()
            if old and not old.deleted and (old.digest, old.title, old.effective, old.expires, old.pages, old.family) == (digest, title, effective, expires, pages, family):
                return old
            document = Document(identifier, actor.tenant, title, 1 if old is None else old.version + 1, text, digest, pages, effective, expires, family)
            self.repo.put_document(document)
            self.repo.record(actor.tenant, actor.id, 'document_ingested', identifier)
            return document

    @repository_scope
    def read_version(self, actor, identifier, version):
        with self.repo.lock:
            self._document(actor, identifier)  # Current access/deletion controls historical reads too.
            result = self.repo.document_version(actor.tenant, identifier, version)
            if result is None:
                raise DomainError('document_not_found', 404)
            return result

    @repository_scope
    def delete(self, actor, identifier):
        if actor.role != 'service_manager':
            raise DomainError('forbidden')
        with self.repo.lock:
            document = self._document(actor, identifier)
            self.repo.put_document(replace(document, deleted=True))
            self.repo.record(actor.tenant, actor.id, 'document_deleted', identifier)

    @repository_scope
    def search(self, actor, query, as_of=None, limit=5):
        from backend.retrieval import keyword_search
        # Re-read authorized current documents on every call: no stale shared index/cache.
        with self.repo.lock:
            return keyword_search(self.list_documents(actor), query, as_of or date.today(), limit)

    @repository_scope
    def change_access(self, actor, target, identifier, revoked):
        if actor.role != 'administrator' or actor.tenant != target.tenant:
            raise DomainError('forbidden')
        with self.repo.lock:
            document=self.repo.document(actor.tenant,identifier)
            if document is None or document.deleted:
                raise DomainError('document_not_found',404)
            # Restore may only remove a revocation; it never widens original profile grants.
            self.repo.set_revoked(actor.tenant,target.id,identifier,revoked)
            if revoked:
                for proposal in self.repo.proposals(actor.tenant):
                    if target.id in {proposal.actor_id,proposal.approver_id} and any(s[0]==identifier for s in proposal.source_versions):
                        self.repo.put_proposal(replace(proposal,status='stale',approver_id=None))
            self.repo.record(actor.tenant,actor.id,'access_revoked' if revoked else 'access_restored',identifier)

    @repository_scope
    def prepare(self, actor, identifiers, steps, expected_versions=None):
        if actor.role not in self.READ_ROLES:
            raise DomainError('forbidden')
        with self.repo.lock:
            sources = [self._document(actor, identifier) for identifier in sorted(set(identifiers))]
            if not sources or not steps:
                raise DomainError('empty_proposal', 422)
            if expected_versions is not None and expected_versions != {s.id:s.version for s in sources}:
                raise DomainError('source_changed_or_expired',409)
            today = date.today().isoformat()
            for source in sources:
                if ((source.effective and source.effective > today) or (source.expires and source.expires < today)
                    or any(p.quality != 'usable' for p in source.pages)):
                    raise DomainError('source_requires_review', 409)
                if source.family and any(d.id != source.id and d.family == source.family and d.digest != source.digest
                                         and (not d.effective or d.effective <= today) and (not d.expires or d.expires >= today)
                                         for d in self.list_documents(actor)):
                    raise DomainError('source_conflict', 409)
            citations = []
            for step in steps:
                match = next(((s.id,s.version,p.number,p.text.index(step),p.text.index(step)+len(step))
                              for s in sources for p in s.pages if step.strip() and step in p.text),None)
                if match is None:
                    raise DomainError('unsupported_step', 422)
                citations.append(match)
            versions = tuple((d.id, d.version, d.digest) for d in sources)
            payload = {'tenant': actor.tenant, 'sources': versions, 'steps': steps, 'citations': citations}
            digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
            proposal = Proposal(str(uuid4()), actor.tenant, actor.id, versions, tuple(steps), digest,
                                datetime.now(timezone.utc) + timedelta(minutes=30), tuple(citations))
            self.repo.put_proposal(proposal)
            self.repo.record(actor.tenant, actor.id, 'checklist_prepared', proposal.id)
            return proposal

    def _proposal(self, actor, identifier):
        proposal = self.repo.proposal(actor.tenant, identifier)
        if proposal is None or actor.role not in self.READ_ROLES:
            raise DomainError('proposal_not_found', 404)
        for document_id, _, _ in proposal.source_versions:
            self._document(actor, document_id)
        return proposal

    @repository_scope
    def read_proposal(self, actor, identifier):
        with self.repo.lock:
            proposal = self._proposal(actor, identifier)
            drift = any((d := self._document(actor, doc_id)).version != version or d.digest != digest
                        for doc_id, version, digest in proposal.source_versions)
            today = date.today().isoformat()
            for doc_id, _, _ in proposal.source_versions:
                source = self._document(actor, doc_id)
                drift = drift or self.repo.is_revoked(actor.tenant,proposal.actor_id,doc_id)
                if proposal.approver_id:
                    drift = drift or self.repo.is_revoked(actor.tenant,proposal.approver_id,doc_id)
                drift = drift or bool((source.expires and source.expires < today) or
                                      (source.effective and source.effective > today) or
                                      any(p.quality != 'usable' for p in source.pages))
                if source.family:
                    drift = drift or any(d.id != source.id and d.family == source.family and d.digest != source.digest
                                         and (not d.effective or d.effective <= today) and (not d.expires or d.expires >= today)
                                         for d in self.list_documents(actor))
            if drift or datetime.now(timezone.utc) >= proposal.expires_at:
                return replace(proposal, status='stale', approver_id=None)
            return proposal

    @repository_scope
    def list_proposals(self, actor):
        if actor.role not in self.READ_ROLES:
            raise DomainError('forbidden')
        with self.repo.lock:
            result = []
            for proposal in self.repo.proposals(actor.tenant):
                try:
                    result.append(self.read_proposal(actor, proposal.id))
                except DomainError as error:
                    if error.status != 404:
                        raise
            return result

    @repository_scope
    def approve(self, actor, identifier, payload_hash):
        if actor.role != 'service_manager':
            raise DomainError('forbidden')
        with self.repo.lock:
            proposal = self.read_proposal(actor, identifier)
            if proposal.actor_id == actor.id:
                raise DomainError('self_approval')
            if proposal.payload_hash != payload_hash:
                raise DomainError('payload_changed', 409)
            if proposal.status == 'stale':
                raise DomainError('source_changed_or_expired', 409)
            if proposal.status != 'review':
                raise DomainError('already_reviewed', 409)
            approved = replace(proposal, status='approved', approver_id=actor.id)
            self.repo.put_proposal(approved)
            self.repo.record(actor.tenant, actor.id, 'checklist_approved', identifier)
            return approved

    @repository_scope
    def audit(self, actor):
        if actor.role not in {'auditor', 'administrator'}:
            raise DomainError('forbidden')
        with self.repo.lock:
            return self.repo.events(actor.tenant)
