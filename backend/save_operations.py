"""Save state machine on a memory contract harness; never production durability."""
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import json
from threading import RLock
from typing import Protocol
from uuid import uuid4

from backend.domain import Actor, DomainError
from backend.odoo_contract import Target, canonical, prepare_save_payload, require_capability, verify_receipt


class ChecklistBridge(Protocol):
    def info(self) -> dict: ...
    def execute(self, envelope: dict) -> dict: ...
    def status(self, tenant: str, company_id: int, operation_id: str) -> dict | None: ...


@dataclass(frozen=True)
class SaveOperation:
    id: str
    tenant: str
    proposal_id: str
    requested_by: Actor
    payload_json: str
    payload_hash: str
    expires_at: datetime
    status: str = 'review'
    approved_by: Actor | None = None
    attempts: int = 0
    external_id: int | None = None
    error: str | None = None


class MemorySaveLedger:
    """Test/native harness only. Lost at restart; cannot be used for live writes."""
    def __init__(self):
        self.lock = RLock()
        self.operations = {}
        self.by_proposal = {}


class SaveOperations:
    def __init__(self, service, ledger: MemorySaveLedger, targets: dict[str, Target], bridge: ChecklistBridge,
                 clock=lambda: datetime.now(timezone.utc)):
        if getattr(bridge, 'requires_durable_ledger', False):
            # Persistent coordinator is not wired yet. Reject even before capability
            # checks so a transport cannot accidentally turn harness tests into writes.
            raise DomainError('durable_save_coordinator_required', 503)
        self.service, self.ledger, self.targets, self.bridge, self.clock = service, ledger, targets, bridge, clock

    def _store(self, operation):
        self.ledger.operations[(operation.tenant, operation.id)] = operation
        return operation

    def _read(self, actor, identifier):
        if actor.role != 'service_manager':
            raise DomainError('forbidden')
        op = self.ledger.operations.get((actor.tenant, identifier))
        if op is None:
            raise DomainError('operation_not_found', 404)
        self.service.read_proposal(actor, op.proposal_id)  # Current grants even for historical recovery.
        return op

    def read(self, actor, identifier):
        with self.ledger.lock, self.service.repo.lock:
            return self._read(actor, identifier)

    def _current(self, actor, op):
        if self.clock() >= op.expires_at:
            raise DomainError('save_approval_expired', 409)
        target = self.targets.get(actor.tenant)
        if target is None:
            raise DomainError('odoo_target_unavailable', 503)
        # Revocation of the requesting/reviewing identity invalidates dispatch too.
        for principal in (actor, op.requested_by, op.approved_by):
            if principal is None:
                continue
            preview = prepare_save_payload(self.service, principal, op.proposal_id, target)
            if preview['payload_hash'] != op.payload_hash:
                raise DomainError('save_payload_changed', 409)

    def prepare(self, actor, proposal_id):
        with self.ledger.lock, self.service.repo.lock:
            target = self.targets.get(actor.tenant)
            if target is None:
                raise DomainError('odoo_target_unavailable', 503)
            preview = prepare_save_payload(self.service, actor, proposal_id, target)
            existing = self.ledger.by_proposal.get((actor.tenant, proposal_id))
            if existing:
                op = self._read(actor, existing)
                if op.payload_hash != preview['payload_hash']:
                    raise DomainError('save_payload_changed', 409)
                return op  # A fresh client retry cannot allocate a second operation.
            op = SaveOperation(str(uuid4()), actor.tenant, proposal_id, actor,
                               canonical(preview['payload']), preview['payload_hash'],
                               self.clock() + timedelta(minutes=30))
            self.ledger.by_proposal[(actor.tenant, proposal_id)] = op.id
            self.service.repo.record(actor.tenant, actor.id, 'save_prepared', op.id)
            return self._store(op)

    def approve(self, actor, identifier, payload_hash):
        with self.ledger.lock, self.service.repo.lock:
            op = self._read(actor, identifier)
            if actor.id in {op.requested_by.id, json.loads(op.payload_json)['prepared_by']}:
                raise DomainError('self_approval')
            if op.status != 'review' or op.attempts:
                raise DomainError('already_reviewed', 409)
            if payload_hash != op.payload_hash:
                raise DomainError('save_payload_changed', 409)
            self._current(actor, op)
            self.service.repo.record(actor.tenant, actor.id, 'save_approved', op.id)
            return self._store(replace(op, approved_by=actor, status='approved'))

    def save(self, actor, identifier):
        with self.ledger.lock, self.service.repo.lock:
            op = self._read(actor, identifier)
            if op.status == 'verified':
                return op
            if op.status in {'unknown', 'dispatched'}:
                return self._reconcile(actor, op)  # Read-only recovery, never redispatch.
            if op.status != 'approved' or op.approved_by is None:
                raise DomainError('destination_approval_required', 409)
            self._current(actor, op)
            require_capability(self.bridge.info())
            op = self._store(replace(op, status='dispatched', attempts=op.attempts+1))
            envelope = {'operation_id':op.id, 'payload_hash':op.payload_hash,
                        'payload':json.loads(op.payload_json), 'requested_by':op.requested_by.id,
                        'approved_by':op.approved_by.id, 'expires_at':op.expires_at.isoformat()}
            self.service.repo.record(actor.tenant, actor.id, 'save_dispatched', op.id)
            try:
                self.bridge.execute(envelope)
            except Exception:
                self._store(replace(op, status='unknown', error='dispatch_outcome_unknown'))
                return self.ledger.operations[(op.tenant, op.id)]
            # Execute response is never sufficient; independently read back.
            return self._reconcile(actor, op)

    def reconcile(self, actor, identifier):
        with self.ledger.lock, self.service.repo.lock:
            op = self._read(actor, identifier)
            if not op.attempts:
                raise DomainError('operation_not_dispatched', 409)
            return self._reconcile(actor, op)

    def _reconcile(self, actor, op):
        payload = json.loads(op.payload_json)
        try:
            receipt = self.bridge.status(op.tenant, payload['target']['company_id'], op.id)
        except Exception:
            return self._store(replace(op, status='unknown', external_id=None, error='readback_unavailable'))
        if receipt is None:
            return self._store(replace(op, status='unknown', external_id=None, error='receipt_not_found'))
        try:
            external = verify_receipt(receipt, op.id, payload)
        except (DomainError, TypeError, ValueError):
            return self._store(replace(op, status='review', external_id=None, error='odoo_readback_mismatch'))
        self.service.repo.record(actor.tenant, actor.id, 'save_verified', op.id)
        return self._store(replace(op, status='verified', external_id=external, error=None))
