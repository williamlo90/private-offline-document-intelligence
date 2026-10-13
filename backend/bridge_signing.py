"""Signed extension-envelope contract; receiver integration is still pending."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import hmac
from uuid import UUID

from backend.domain import DomainError
from backend.odoo_contract import canonical, fingerprint, CONTRACT_VERSION, UPSTREAM_REVISION

ENVELOPE_KEYS = {'operation_id', 'payload_hash', 'payload', 'requested_by', 'approved_by', 'expires_at'}
PAYLOAD_KEYS = {'contract_version', 'upstream_revision', 'tenant', 'target', 'proposal_id',
                'proposal_hash', 'prepared_by', 'reviewed_by', 'steps', 'source_versions', 'step_sources'}


def sign_envelope(envelope, key: bytes):
    if len(key) < 32:
        raise DomainError('bridge_key_unavailable', 503)
    raw = canonical(envelope).encode()
    if len(raw) > 110_000:
        raise DomainError('bridge_envelope_limit', 422)
    return hmac.new(key, raw, hashlib.sha256).hexdigest()


def verify_envelope(envelope, signature, key: bytes, tenant: str, company_id: int, now=None):
    if not isinstance(signature, str) or not hmac.compare_digest(sign_envelope(envelope, key), signature):
        raise DomainError('invalid_signature')
    try:
        if set(envelope) != ENVELOPE_KEYS or set(envelope['payload']) != PAYLOAD_KEYS:
            raise ValueError()
        payload = envelope['payload']
        UUID(envelope['operation_id']); UUID(payload['proposal_id'])
        if payload['contract_version'] != CONTRACT_VERSION or payload['upstream_revision'] != UPSTREAM_REVISION:
            raise ValueError()
        if envelope['payload_hash'] != fingerprint(payload):
            raise ValueError()
        if payload['tenant'] != tenant or type(payload['target']['company_id']) is not int or payload['target']['company_id'] != company_id:
            raise DomainError('scope_mismatch')
        actors = [envelope['requested_by'], envelope['approved_by'], payload['prepared_by'], payload['reviewed_by']]
        if any(not isinstance(actor, str) or not 1 <= len(actor) <= 100 for actor in actors):
            raise ValueError()
        if envelope['approved_by'] in {envelope['requested_by'], payload['prepared_by']} or payload['prepared_by'] == payload['reviewed_by']:
            raise DomainError('self_approval')
        expiry = datetime.fromisoformat(envelope['expires_at'])
        if expiry.tzinfo is None or expiry <= (now or datetime.now(timezone.utc)):
            raise DomainError('save_approval_expired', 409)
    except (TypeError, ValueError, KeyError, AttributeError):
        raise DomainError('invalid_bridge_envelope', 422) from None
    return deepcopy(envelope)
