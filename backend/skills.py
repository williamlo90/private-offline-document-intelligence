"""Shared executable business capabilities. Identity is supplied by the transport."""
import hashlib
from pathlib import Path
import time
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from backend.domain import DomainError, Proposal
from backend.assistant_contracts import SourceAssistant, Question, Extraction, SourceResult


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class PrepareChecklist(Contract):
    document_ids: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(min_length=1, max_length=10)
    steps: list[Annotated[str, Field(min_length=1, max_length=2000)]] = Field(min_length=1, max_length=30)
    expected_versions: dict[str, Annotated[int, Field(ge=1)]] = Field(min_length=1, max_length=10)


class AuditReadiness(Contract):
    pass  # No caller-controlled filesystem paths or asserted network status.


class Artifact(Contract):
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,100}$')
    path: str = Field(min_length=1, max_length=300)
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


class BundleManifest(Contract):
    schema_version: Literal['1.0']
    artifacts: list[Artifact] = Field(min_length=1, max_length=100)
    components: dict[str, list[str]] = Field(default_factory=dict, max_length=20)


BUNDLE_COMPONENTS = ('application', 'python_runtime', 'python_packages', 'node_runtime',
                     'node_packages', 'ocr_runtime', 'ocr_languages', 'tokenizer', 'embeddings',
                     'ollama_runtime', 'generative_model', 'licenses')


class ArtifactCheck(Contract):
    id: str
    status: Literal['verified', 'missing_or_unsafe', 'checksum_mismatch', 'budget_exceeded']


class ReadinessResult(Contract):
    schema_version: Literal['1.0'] = '1.0'
    status: Literal['manifest_missing', 'manifest_invalid', 'assets_incomplete', 'assets_verified']
    checks: list[ArtifactCheck] = Field(default_factory=list)
    offline_validated: Literal[False] = False
    pending: list[str] = Field(default_factory=lambda: ['native_cold_start', 'isolated_network_boundary', 'runtime_health'])


class BusinessSkills:
    def __init__(self, service, bundle_root: Path, generator=None):
        self.service = service
        self.bundle_root = bundle_root.resolve()
        self.assistant = SourceAssistant(service, generator)

    def answer_client_question(self, actor, request: Question, **options) -> SourceResult:
        return self.assistant.run(actor, request, **options)

    def extract_service_terms(self, actor, request: Extraction, **options) -> SourceResult:
        return self.assistant.run(actor, request, **options)

    def prepare_service_checklist(self, actor, request: PrepareChecklist) -> Proposal:
        # Source, ACL, review, expiry and conflict rules have one owner.
        return self.service.prepare(actor, request.document_ids, request.steps, request.expected_versions)

    def audit_offline_readiness(self, actor, request: AuditReadiness, *, cancelled=lambda: False) -> ReadinessResult:
        if actor.role != 'administrator':
            raise DomainError('forbidden')
        # A quantized model and its runtime exceed 2 GiB; keep verification bounded
        # without making an otherwise complete local inventory impossible to audit.
        deadline = time.monotonic() + 120
        manifest_path = self.bundle_root / 'manifest.json'
        try:
            if manifest_path.resolve().parent != self.bundle_root or manifest_path.stat().st_size > 100_000:
                return ReadinessResult(status='manifest_invalid')
            manifest = BundleManifest.model_validate_json(manifest_path.read_bytes())
            if len({a.id for a in manifest.artifacts}) != len(manifest.artifacts):
                return ReadinessResult(status='manifest_invalid')
            identifiers={a.id for a in manifest.artifacts}
            if (set(manifest.components)-set(BUNDLE_COMPONENTS) or
                any(not set(ids)<=identifiers for ids in manifest.components.values())):
                return ReadinessResult(status='manifest_invalid')
        except FileNotFoundError:
            return ReadinessResult(status='manifest_missing')
        except (OSError, ValidationError, ValueError):
            return ReadinessResult(status='manifest_invalid')
        checks, consumed = [], 0
        for artifact in manifest.artifacts:
            if cancelled():
                raise DomainError('operation_cancelled', 409)
            status = 'missing_or_unsafe'
            try:
                relative = Path(artifact.path)
                candidate = (self.bundle_root / relative).resolve()
                # Reject traversal, absolute paths and NTFS alternate data streams.
                if relative.is_absolute() or '..' in relative.parts or ':' in artifact.path or not candidate.is_relative_to(self.bundle_root) or not candidate.is_file():
                    raise ValueError('unsafe path')
                digest = hashlib.sha256()
                with candidate.open('rb') as stream:
                    while chunk := stream.read(1024 * 1024):
                        consumed += len(chunk)
                        if cancelled():
                            raise DomainError('operation_cancelled', 409)
                        if consumed > 8 * 1024**3 or time.monotonic() > deadline:
                            status = 'budget_exceeded'
                            break
                        digest.update(chunk)
                    else:
                        status = 'verified' if digest.hexdigest() == artifact.sha256 else 'checksum_mismatch'
            except (OSError, ValueError):
                pass
            checks.append(ArtifactCheck(id=artifact.id, status=status))
            if status == 'budget_exceeded':
                break
        complete = len(checks) == len(manifest.artifacts) and all(c.status == 'verified' for c in checks)
        result = ReadinessResult(status='assets_verified' if complete else 'assets_incomplete', checks=checks)
        verified={c.id for c in checks if c.status=='verified'}
        result.pending.extend('component:'+name for name in BUNDLE_COMPONENTS
                              if not manifest.components.get(name) or not set(manifest.components[name])<=verified)
        self.service.repo.record(actor.tenant, actor.id, 'offline_readiness_checked', result.status)
        return result


def schemas():
    from pydantic import TypeAdapter
    return {
        'answer_client_question': {'input': Question.model_json_schema(), 'output': SourceResult.model_json_schema()},
        'extract_service_terms': {'input': Extraction.model_json_schema(), 'output': SourceResult.model_json_schema()},
        'prepare_service_checklist': {'input': PrepareChecklist.model_json_schema(), 'output': TypeAdapter(Proposal).json_schema()},
        'audit_offline_readiness': {'input': AuditReadiness.model_json_schema(), 'output': ReadinessResult.model_json_schema()},
    }
