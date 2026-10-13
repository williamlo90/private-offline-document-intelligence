"""Durable, approval-bound Odoo dispatch with one committed claim and read-back."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
from uuid import uuid4

import psycopg

from backend.domain import Actor, DomainError
from backend.odoo_contract import canonical, prepare_save_payload, require_capability, verify_receipt
from backend.save_operations import SaveOperation
from backend.save_repository import PostgresSaveRepository


class PersistentSaveOperations:
    def __init__(self, service, targets, bridges, *, clock=lambda: datetime.now(timezone.utc)):
        if not all(getattr(bridge, "requires_durable_ledger", False) for bridge in bridges.values()):
            raise ValueError("Persistent coordinator requires the signed live bridge")
        self.service, self.targets, self.bridges, self.clock = service, targets, bridges, clock
        self.config = dict(service.repo.config)
        self.actors = {(actor.tenant, actor.id): actor for actor in service.repo.actors}

    @contextmanager
    def _store(self):
        with psycopg.connect(**self.config, autocommit=True, connect_timeout=5) as connection:
            yield PostgresSaveRepository(connection)

    def _principal(self, tenant, identifier):
        actor = self.actors.get((tenant, identifier))
        if actor is None:
            raise DomainError("operation_not_found", 404)
        return actor

    def _decode(self, tenant, row):
        return SaveOperation(str(row[0]), tenant, str(row[1]),
            self._principal(tenant, row[2]), canonical(row[4]), row[5], row[7],
            row[6], self._principal(tenant, row[3]) if row[3] else None,
            row[8], row[10], row[11])

    def _read_raw(self, actor, identifier):
        if actor.role != "service_manager":
            raise DomainError("forbidden")
        with self._store() as store:
            row = store.read(actor, identifier)
        operation = self._decode(actor.tenant, row)
        self.service.read_proposal(actor, operation.proposal_id)
        return operation, row[9]

    def read(self, actor, identifier):
        return self._read_raw(actor, identifier)[0]

    def _current(self, actor, operation):
        if self.clock() >= operation.expires_at:
            raise DomainError("save_approval_expired", 409)
        target = self.targets.get(actor.tenant)
        if target is None:
            raise DomainError("odoo_target_unavailable", 503)
        for principal in (actor, operation.requested_by, operation.approved_by):
            if principal is None:
                continue
            preview = prepare_save_payload(self.service, principal, operation.proposal_id, target)
            if preview["payload_hash"] != operation.payload_hash:
                raise DomainError("save_payload_changed", 409)

    def prepare(self, actor, proposal_id):
        if actor.role != "service_manager":
            raise DomainError("forbidden")
        target = self.targets.get(actor.tenant)
        if target is None:
            raise DomainError("odoo_target_unavailable", 503)
        preview = prepare_save_payload(self.service, actor, proposal_id, target)
        with self._store() as store:
            existing = store.read_by_proposal(actor, proposal_id)
        if existing:
            operation = self._decode(actor.tenant, existing)
            if operation.payload_hash != preview["payload_hash"]:
                raise DomainError("save_payload_changed", 409)
            return operation
        operation = SaveOperation(str(uuid4()), actor.tenant, proposal_id, actor,
                                  canonical(preview["payload"]), preview["payload_hash"],
                                  self.clock() + timedelta(minutes=30))
        with self._store() as store:
            store.insert_preview(actor, operation)
        self.service.repo.record(actor.tenant, actor.id, "save_prepared", operation.id)
        return operation

    def approve(self, actor, identifier, payload_hash):
        operation, revision = self._read_raw(actor, identifier)
        if operation.status != "review" or operation.attempts:
            raise DomainError("already_reviewed", 409)
        if payload_hash != operation.payload_hash:
            raise DomainError("save_payload_changed", 409)
        if actor.id in {operation.requested_by.id, json.loads(operation.payload_json)["prepared_by"]}:
            raise DomainError("self_approval")
        self._current(actor, operation)
        with self._store() as store:
            store.approve(actor, identifier, revision, payload_hash)
        self.service.repo.record(actor.tenant, actor.id, "save_approved", identifier)
        return self.read(actor, identifier)

    def save(self, actor, identifier):
        operation, revision = self._read_raw(actor, identifier)
        if operation.status == "verified":
            return operation
        if operation.status in {"dispatched", "unknown"}:
            return self.reconcile(actor, identifier)
        if operation.status != "approved" or operation.approved_by is None:
            raise DomainError("destination_approval_required", 409)
        self._current(actor, operation)
        bridge = self.bridges.get(actor.tenant)
        if bridge is None:
            raise DomainError("odoo_target_unavailable", 503)
        require_capability(bridge.info())
        with self._store() as store:
            store.claim_dispatch(actor, identifier, revision, operation.payload_hash)
        # The one-shot claim has committed before the external call begins.
        self.service.repo.record(actor.tenant, actor.id, "save_dispatched", identifier)
        envelope = {"operation_id": operation.id, "payload_hash": operation.payload_hash,
                    "payload": json.loads(operation.payload_json),
                    "requested_by": operation.requested_by.id,
                    "approved_by": operation.approved_by.id,
                    "expires_at": operation.expires_at.isoformat()}
        try:
            bridge.execute(envelope)
        except Exception:
            self._record_readback(actor, identifier, "unknown", error="dispatch_outcome_unknown")
            return self.read(actor, identifier)
        return self.reconcile(actor, identifier)

    def _record_readback(self, actor, identifier, status, *, external_id=None, error=None):
        _, revision = self._read_raw(actor, identifier)
        with self._store() as store:
            store.record_readback(actor, identifier, revision, status=status,
                                  external_id=external_id, error=error)

    def reconcile(self, actor, identifier):
        operation, _ = self._read_raw(actor, identifier)
        if operation.status == "verified":
            return operation
        if not operation.attempts:
            raise DomainError("operation_not_dispatched", 409)
        bridge = self.bridges.get(actor.tenant)
        if bridge is None:
            raise DomainError("odoo_target_unavailable", 503)
        payload = json.loads(operation.payload_json)
        try:
            receipt = bridge.status(operation.tenant, payload["target"]["company_id"], operation.id)
        except Exception:
            self._record_readback(actor, identifier, "unknown", error="readback_unavailable")
            return self.read(actor, identifier)
        if receipt is None:
            self._record_readback(actor, identifier, "unknown", error="receipt_not_found")
            return self.read(actor, identifier)
        try:
            external_id = verify_receipt(receipt, operation.id, payload)
        except (DomainError, TypeError, ValueError):
            self._record_readback(actor, identifier, "review", error="odoo_readback_mismatch")
            return self.read(actor, identifier)
        self._record_readback(actor, identifier, "verified", external_id=external_id)
        self.service.repo.record(actor.tenant, actor.id, "save_verified", identifier)
        return self.read(actor, identifier)
