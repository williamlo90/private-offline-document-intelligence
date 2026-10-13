"""Persistent project-07 domain repository; every transaction uses an app RLS role."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict
from datetime import datetime, timezone
import json
from threading import RLock, local

import psycopg

from backend.domain import Actor, Document, DomainError, Proposal
from backend.pdf_parser import Page


class _TransactionLock:
    def __init__(self, repo):
        self.repo = repo
        self.mutex = RLock()
        self.state = local()

    def __enter__(self):
        self.mutex.acquire()
        if getattr(self.state, "depth", 0):
            self.state.depth += 1
            return self
        actor = self.repo._actor.get()
        if actor is None:
            self.mutex.release()
            raise RuntimeError("Persistent repository requires an authenticated actor")
        try:
            conn = psycopg.connect(**self.repo.config, autocommit=True, connect_timeout=5)
            transaction = conn.transaction()
            transaction.__enter__()
            conn.execute("SELECT set_config('app.tenant_id', %s, true), set_config('app.actor_id', %s, true)",
                         (actor.tenant, actor.id))
        except BaseException:
            if 'conn' in locals():
                conn.close()
            self.mutex.release()
            raise
        self.state.conn = conn
        self.state.transaction = transaction
        self.state.depth = 1
        return self

    def __exit__(self, exc_type, exc, traceback):
        try:
            self.state.depth -= 1
            if self.state.depth == 0:
                try:
                    self.state.transaction.__exit__(exc_type, exc, traceback)
                finally:
                    self.state.conn.close()
                    del self.state.conn
                    del self.state.transaction
        finally:
            self.mutex.release()


class PostgresRepository:
    def __init__(self, config: dict, actors: list[Actor]):
        if config.get("dbname") != "private_documents_lab" or config.get("host") not in {"127.0.0.1", "database"}:
            raise ValueError("Expected isolated Phase 7 lab database")
        self.config = dict(config)
        self.actors = tuple(actors)
        self._actor: ContextVar[Actor | None] = ContextVar("project07_db_actor", default=None)
        self.lock = _TransactionLock(self)

    @contextmanager
    def scoped(self, actor: Actor):
        token = self._actor.set(actor)
        try:
            yield
        finally:
            self._actor.reset(token)

    @property
    def _conn(self):
        conn = getattr(self.lock.state, "conn", None)
        if conn is None:
            raise RuntimeError("Persistent repository operation outside a transaction")
        return conn

    def _within(self, actor: Actor, method, *args):
        if getattr(self.lock.state, "conn", None) is not None:
            return method(*args)
        with self.scoped(actor), self.lock:
            return method(*args)

    @staticmethod
    def _document(row) -> Document:
        snapshot, deleted, identifier, tenant, title, version, body, digest, effective, expires = row
        if snapshot:
            snapshot = dict(snapshot)
            snapshot["pages"] = tuple(Page(**page) for page in snapshot.get("pages", []))
            snapshot["deleted"] = deleted
            return Document(**snapshot)
        # Explicit fallback for records created before migration 004.
        return Document(identifier, tenant, title, version, body, digest, (Page(1, body),),
                        effective.isoformat() if effective else None,
                        expires.isoformat() if expires else None, deleted=deleted)

    def _document_query(self, tenant: str, identifier: str, version: int | None = None):
        row = self._conn.execute('''SELECT v.snapshot,d.deleted,d.id,d.tenant_id,d.title,v.version,
                   v.body,v.content_hash,v.effective_date,v.expires_date
                   FROM documents d JOIN document_versions v ON v.tenant_id=d.tenant_id
                   AND v.document_id=d.id AND v.version=COALESCE(%s,d.current_version)
                   WHERE d.tenant_id=%s AND d.id=%s''', (version, tenant, identifier)).fetchone()
        return self._document(row) if row else None

    def documents(self, tenant: str) -> list[Document]:
        rows = self._conn.execute('''SELECT v.snapshot,d.deleted,d.id,d.tenant_id,d.title,v.version,
                   v.body,v.content_hash,v.effective_date,v.expires_date
                   FROM documents d JOIN document_versions v ON v.tenant_id=d.tenant_id
                   AND v.document_id=d.id AND v.version=d.current_version WHERE d.tenant_id=%s
                   ORDER BY d.id''', (tenant,)).fetchall()
        return [self._document(row) for row in rows]

    def tenant_ids(self) -> set[str]:
        return {actor.tenant for actor in self.actors}

    def document(self, tenant: str, identifier: str) -> Document | None:
        return self._document_query(tenant, identifier)

    def document_version(self, tenant: str, identifier: str, version: int) -> Document | None:
        return self._document_query(tenant, identifier, version)

    def put_document(self, document: Document) -> None:
        payload = json.dumps(asdict(document), ensure_ascii=False)
        conn = self._conn
        if document.version == 1:
            inserted = conn.execute('''INSERT INTO documents(tenant_id,id,title,current_version,deleted)
                VALUES (%s,%s,%s,1,%s) ON CONFLICT DO NOTHING''',
                (document.tenant, document.id, document.title, document.deleted))
            if inserted.rowcount != 1:
                raise DomainError("source_changed_or_expired", 409)
            conn.execute('''INSERT INTO document_versions
                (tenant_id,document_id,version,content_hash,body,effective_date,expires_date,snapshot)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)''',
                (document.tenant, document.id, document.version, document.digest, document.text,
                 document.effective, document.expires, payload))
            return
        if document.deleted:
            row = conn.execute('''UPDATE documents SET deleted=true WHERE tenant_id=%s AND id=%s
                AND current_version=%s AND deleted=false RETURNING id''',
                (document.tenant, document.id, document.version)).fetchone()
            if row is None:
                raise DomainError("source_changed_or_expired", 409)
            return
        row = conn.execute('''UPDATE documents SET title=%s,current_version=%s,deleted=false
            WHERE tenant_id=%s AND id=%s AND current_version=%s RETURNING id''',
            (document.title, document.version, document.tenant, document.id, document.version - 1)).fetchone()
        if row is None:
            raise DomainError("source_changed_or_expired", 409)
        conn.execute('''INSERT INTO document_versions
            (tenant_id,document_id,version,content_hash,body,effective_date,expires_date,snapshot)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)''',
            (document.tenant, document.id, document.version, document.digest, document.text,
             document.effective, document.expires, payload))

    @staticmethod
    def _proposal(row) -> Proposal:
        payload, status, approver_id = row
        return Proposal(payload["id"], payload["tenant"], payload["actor_id"],
                        tuple(tuple(item) for item in payload["source_versions"]),
                        tuple(payload["steps"]), payload["payload_hash"],
                        datetime.fromisoformat(payload["expires_at"]),
                        tuple(tuple(item) for item in payload.get("step_sources", [])),
                        status, approver_id)

    def proposal(self, tenant: str, identifier: str) -> Proposal | None:
        row = self._conn.execute('''SELECT payload,status,approver_id FROM checklist_proposals
            WHERE tenant_id=%s AND id=%s''', (tenant, identifier)).fetchone()
        return self._proposal(row) if row else None

    def proposals(self, tenant: str) -> list[Proposal]:
        rows = self._conn.execute('''SELECT payload,status,approver_id FROM checklist_proposals
            WHERE tenant_id=%s ORDER BY created_at''', (tenant,)).fetchall()
        return [self._proposal(row) for row in rows]

    def put_proposal(self, proposal: Proposal) -> None:
        payload = asdict(proposal)
        payload["expires_at"] = proposal.expires_at.isoformat()
        encoded = json.dumps(payload, ensure_ascii=False)
        if proposal.status == "review":
            self._conn.execute('''INSERT INTO checklist_proposals
                (tenant_id,id,actor_id,payload,payload_hash,status,expires_at)
                VALUES (%s,%s,%s,%s::jsonb,%s,'review',%s)''',
                (proposal.tenant, proposal.id, proposal.actor_id, encoded,
                 proposal.payload_hash, proposal.expires_at))
            for identifier, version, _ in proposal.source_versions:
                self._conn.execute('''INSERT INTO proposal_sources
                    (tenant_id,proposal_id,document_id,version) VALUES (%s,%s,%s,%s)''',
                    (proposal.tenant, proposal.id, identifier, version))
        else:
            row = self._conn.execute('''UPDATE checklist_proposals SET status=%s,approver_id=%s,
                payload=%s::jsonb WHERE tenant_id=%s AND id=%s AND payload_hash=%s
                RETURNING id''', (proposal.status, proposal.approver_id, encoded, proposal.tenant,
                                 proposal.id, proposal.payload_hash)).fetchone()
            if row is None:
                raise DomainError("source_changed_or_expired", 409)
            if proposal.status == "approved":
                self._conn.execute('''INSERT INTO approvals
                    (tenant_id,proposal_id,payload_hash,approver_id) VALUES (%s,%s,%s,%s)
                    ON CONFLICT DO NOTHING''',
                    (proposal.tenant, proposal.id, proposal.payload_hash, proposal.approver_id))

    def record(self, tenant: str, actor: str, action: str, resource: str) -> None:
        def write():
            self._conn.execute('''INSERT INTO audit_events(tenant_id,actor_id,action,resource_id)
                VALUES (%s,%s,%s,%s)''', (tenant, actor, action, resource))
        self._within(Actor(actor, tenant, "technician"), write)

    def events(self, tenant: str) -> list[dict]:
        rows = self._conn.execute('''SELECT tenant_id,actor_id,action,resource_id,created_at
            FROM audit_events WHERE tenant_id=%s ORDER BY id''', (tenant,)).fetchall()
        return [{"tenant": row[0], "actor": row[1], "action": row[2], "resource": row[3],
                 "at": row[4].astimezone(timezone.utc).isoformat()} for row in rows]

    def is_revoked(self, tenant: str, actor_id: str, document_id: str) -> bool:
        def check():
            return self._conn.execute('''SELECT 1 FROM document_revocations
                WHERE tenant_id=%s AND actor_id=%s AND document_id=%s''',
                (tenant, actor_id, document_id)).fetchone() is not None
        return self._within(Actor(actor_id, tenant, "technician"), check)

    def set_revoked(self, tenant: str, actor_id: str, document_id: str, revoked: bool) -> None:
        if revoked:
            self._conn.execute('''INSERT INTO document_revocations(tenant_id,document_id,actor_id)
                VALUES (%s,%s,%s) ON CONFLICT DO NOTHING''', (tenant, document_id, actor_id))
        else:
            self._conn.execute('''DELETE FROM document_revocations WHERE tenant_id=%s
                AND document_id=%s AND actor_id=%s''', (tenant, document_id, actor_id))
