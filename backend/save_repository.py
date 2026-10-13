"""Prepared PostgreSQL primitives, not yet wired to the memory domain harness."""
from backend.domain import DomainError
from backend.odoo_contract import canonical, fingerprint
import json


class PostgresSaveRepository:
    def __init__(self, connection):
        self.connection = connection

    def _identity(self, cursor, actor):
        if actor.role != 'service_manager':
            raise DomainError('forbidden')
        cursor.execute("SELECT set_config('app.tenant_id', %s, true), set_config('app.actor_id', %s, true)", (actor.tenant, actor.id))

    def insert_preview(self, actor, operation):
        if (operation.tenant != actor.tenant or operation.requested_by != actor or
            operation.status != 'review' or operation.approved_by is not None or operation.attempts):
            raise DomainError('invalid_save_preview', 422)
        payload = json.loads(operation.payload_json)
        if (fingerprint(payload) != operation.payload_hash or payload.get('tenant') != actor.tenant or
            payload.get('proposal_id') != operation.proposal_id):
            raise DomainError('save_payload_changed', 409)
        with self.connection.transaction():
            with self.connection.cursor() as cursor:
                self._identity(cursor, actor)
                cursor.execute('''INSERT INTO save_operations
                    (tenant_id,id,proposal_id,requested_by,payload,payload_hash,status,expires_at)
                    VALUES (%s,%s,%s,%s,%s::jsonb,%s,'review',%s)
                    ON CONFLICT (tenant_id,proposal_id) DO NOTHING
                    RETURNING id,revision,payload,payload_hash''',
                    (actor.tenant, operation.id, operation.proposal_id, actor.id,
                     canonical(payload), operation.payload_hash, operation.expires_at))
                row = cursor.fetchone()
                if row is None:
                    raise DomainError('save_preview_exists', 409)
        return row

    def read(self, actor, operation_id):
        with self.connection.transaction():
            with self.connection.cursor() as cursor:
                self._identity(cursor, actor)
                cursor.execute('''SELECT id,proposal_id,requested_by,approved_by,payload,payload_hash,
                    status,expires_at,attempts,revision,external_id,error_code
                    FROM save_operations WHERE tenant_id=%s AND id=%s''', (actor.tenant,operation_id))
                row = cursor.fetchone()
                if row is None:
                    raise DomainError('operation_not_found',404)
        return row

    def read_by_proposal(self, actor, proposal_id):
        with self.connection.transaction():
            with self.connection.cursor() as cursor:
                self._identity(cursor, actor)
                cursor.execute('''SELECT id,proposal_id,requested_by,approved_by,payload,payload_hash,
                    status,expires_at,attempts,revision,external_id,error_code
                    FROM save_operations WHERE tenant_id=%s AND proposal_id=%s''',
                    (actor.tenant, proposal_id))
                return cursor.fetchone()

    def approve(self, actor, operation_id, expected_revision, expected_hash):
        with self.connection.transaction():
            with self.connection.cursor() as cursor:
                self._identity(cursor, actor)
                cursor.execute('''UPDATE save_operations
                    SET approved_by=%s,status='approved',revision=revision+1,updated_at=now()
                    WHERE tenant_id=%s AND id=%s AND revision=%s AND payload_hash=%s
                      AND status='review' AND attempts=0 AND expires_at>now()
                      AND requested_by<>%s AND payload->>'prepared_by'<>%s
                    RETURNING id,revision,payload,payload_hash''',
                    (actor.id,actor.tenant,operation_id,expected_revision,expected_hash,actor.id,actor.id))
                row=cursor.fetchone()
                if row is None:
                    raise DomainError('save_approval_not_claimed',409)
        return row

    def record_readback(self, actor, operation_id, expected_revision, *, status, external_id=None, error=None):
        errors = {'readback_unavailable','receipt_not_found','odoo_readback_mismatch','dispatch_outcome_unknown'}
        if (status not in {'verified','unknown','review'} or
            (status=='verified' and (type(external_id) is not int or external_id<1 or error is not None)) or
            (status!='verified' and (external_id is not None or error not in errors))):
            raise DomainError('invalid_readback_state',422)
        with self.connection.transaction():
            with self.connection.cursor() as cursor:
                self._identity(cursor, actor)
                cursor.execute('''UPDATE save_operations
                    SET status=%s,external_id=%s,error_code=%s,revision=revision+1,updated_at=now()
                    WHERE tenant_id=%s AND id=%s AND revision=%s AND attempts=1
                      AND status IN ('dispatched','unknown','review','verified')
                    RETURNING id,revision,status,external_id''',
                    (status,external_id,error,actor.tenant,operation_id,expected_revision))
                row=cursor.fetchone()
                if row is None:
                    raise DomainError('save_readback_not_claimed',409)
        return row

    def claim_dispatch(self, actor, operation_id, expected_revision, expected_hash):
        """Commit a compare-and-swap claim before any external call.

        The coordinator must recheck current source/destination approval in its
        persistent domain transaction. This primitive alone is not authorization.
        A failed/uncertain commit means DO NOT call the bridge; reconcile first.
        """
        if actor.role != 'service_manager':
            raise DomainError('forbidden')
        with self.connection.transaction():
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT set_config('app.tenant_id', %s, true), set_config('app.actor_id', %s, true)", (actor.tenant, actor.id))
                cursor.execute('''UPDATE save_operations
                    SET status='dispatched', attempts=1, revision=revision+1, updated_at=now()
                    WHERE tenant_id=%s AND id=%s AND revision=%s AND payload_hash=%s
                      AND status='approved' AND attempts=0 AND approved_by IS NOT NULL AND expires_at>now()
                    RETURNING id, revision, payload, payload_hash''',
                    (actor.tenant, operation_id, expected_revision, expected_hash))
                row = cursor.fetchone()
                if row is None:
                    raise DomainError('save_dispatch_not_claimed', 409)
        # The transaction context has committed before the caller receives a claim.
        return row
