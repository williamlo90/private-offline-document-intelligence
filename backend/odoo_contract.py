"""Project-owned extension contract; not accepted by the upstream v1 activity API."""
import hashlib
import json
from contextlib import nullcontext
from pydantic import BaseModel, ConfigDict, Field
from backend.domain import DomainError

UPSTREAM_REVISION = '6a55b9dc61acd87e61b3aacb4da97d61af84b0fa'
CONTRACT_VERSION = 'private-checklist-1.0'


class Target(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    company_id: int = Field(ge=1)
    customer_id: int = Field(ge=1)
    opportunity_id: int = Field(ge=1)
    assignee_id: int = Field(ge=1)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def require_capability(info):
    # Never squeeze the full checklist into upstream summary<=120 or save a pointer.
    if (not isinstance(info, dict) or info.get('contract_version') != CONTRACT_VERSION or
        info.get('upstream_revision') != UPSTREAM_REVISION or
        info.get('atomic_receipt') is not True or info.get('full_checklist_readback') is not True):
        raise DomainError('odoo_checklist_extension_required', 503)


def prepare_save_payload(service, actor, proposal_id, target: Target):
    """Create a full-content save preview. Target is server configuration, never model input.

    This preview requires its own destination-bound approval before dispatch.
    Existing checklist approval alone does not authorize a mutable Odoo target.
    """
    if actor.role != 'service_manager':
        raise DomainError('forbidden')
    scope = getattr(service.repo, 'scoped', None)
    with scope(actor) if scope else nullcontext(), service.repo.lock:
        proposal = service.read_proposal(actor, proposal_id)
        if proposal.status != 'approved':
            raise DomainError('approved_checklist_required', 409)
        payload = {
            'contract_version':CONTRACT_VERSION, 'upstream_revision':UPSTREAM_REVISION,
            'tenant':actor.tenant, 'target':target.model_dump(),
            'proposal_id':proposal.id, 'proposal_hash':proposal.payload_hash,
            'prepared_by':proposal.actor_id, 'reviewed_by':proposal.approver_id,
            'steps':list(proposal.steps), 'source_versions':[list(s) for s in proposal.source_versions],
            'step_sources':[list(s) for s in proposal.step_sources],
        }
        if len(canonical(payload).encode()) > 100_000:
            raise DomainError('checklist_payload_limit', 422)
        return {'payload':payload, 'payload_hash':fingerprint(payload), 'status':'destination_review_required'}


def verify_receipt(receipt, operation_id, expected_payload):
    """Require exact read-back including scope/content; never infer success from an ID."""
    if not isinstance(receipt, dict) or set(receipt) != {'operation_id','payload_hash','external_id','payload'}:
        raise DomainError('odoo_readback_mismatch', 409)
    if (receipt['operation_id'] != operation_id or type(receipt['external_id']) is not int or
        receipt['external_id'] < 1 or receipt['payload_hash'] != fingerprint(expected_payload) or
        canonical(receipt['payload']) != canonical(expected_payload)):
        raise DomainError('odoo_readback_mismatch', 409)
    return receipt['external_id']
