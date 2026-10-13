"""Bounded local JSON-2 transport for the project-owned Odoo extension."""
import asyncio
import json
from uuid import UUID
import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from backend.bridge_signing import sign_envelope, verify_envelope
from backend.odoo_contract import require_capability


class BridgeProfile(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    port: int = Field(ge=1024, le=65535)
    host: str = Field(default='127.0.0.1', pattern=r'^(127\.0\.0\.1|odoo)$')
    database: str = Field(min_length=1, max_length=100, pattern=r'^[a-zA-Z0-9_-]+$')
    tenant: str = Field(min_length=1, max_length=100)
    company_id: int = Field(ge=1)
    api_key: SecretStr = Field(min_length=24)
    signing_key: SecretStr = Field(min_length=32)
    timeout_seconds: float = Field(default=12.0, gt=0, le=30.0)


class BridgeFailure(Exception):
    def __init__(self, code, uncertain=False):
        self.code, self.uncertain = code, uncertain
        super().__init__(code)


class SignedChecklistBridge:
    requires_durable_ledger = True

    def __init__(self, profile: BridgeProfile, *, transport=None):
        self.profile, self.transport = profile, transport

    def info(self):
        result = self._call('info', {})
        require_capability(result)
        return result

    def execute(self, envelope):
        key = self.profile.signing_key.get_secret_value().encode()
        signature = sign_envelope(envelope, key)
        # Reject wrong scope, approval or expiry before any connection is opened.
        verified = verify_envelope(envelope, signature, key, self.profile.tenant, self.profile.company_id)
        return self._call('execute', {'envelope':verified, 'signature':signature})

    def status(self, tenant, company_id, operation_id):
        if tenant != self.profile.tenant or company_id != self.profile.company_id:
            raise BridgeFailure('scope_mismatch')
        try:
            UUID(operation_id)
        except (ValueError, TypeError, AttributeError):
            raise BridgeFailure('invalid_operation_id') from None
        return self._call('status', {'operation_id':operation_id})

    def _call(self, method, payload):
        if method not in {'info', 'execute', 'status'}:
            raise BridgeFailure('bridge_method_not_allowed')
        try:
            return asyncio.run(self._bounded(method, payload))
        except (TimeoutError, httpx.TimeoutException):
            raise BridgeFailure('bridge_timeout', uncertain=method=='execute') from None
        except httpx.HTTPError:
            raise BridgeFailure('bridge_unavailable', uncertain=method=='execute') from None
        except (ValueError, TypeError):
            raise BridgeFailure('bridge_malformed', uncertain=method=='execute') from None

    async def _bounded(self, method, payload):
        return await asyncio.wait_for(self._request(method, payload), self.profile.timeout_seconds)

    async def _request(self, method, payload):
        async with httpx.AsyncClient(trust_env=False, follow_redirects=False, transport=self.transport,
                                     timeout=httpx.Timeout(30, connect=3)) as client:
            async with client.stream('POST', f'http://{self.profile.host}:{self.profile.port}/json/2/private.checklist.bridge/{method}',
                    headers={'Authorization':'Bearer '+self.profile.api_key.get_secret_value(),
                             'X-Odoo-Database':self.profile.database, 'Accept-Encoding':'identity'}, json=payload) as response:
                if response.status_code != 200:
                    # Never forward Odoo traceback, proxy body or credentials.
                    raise BridgeFailure('bridge_rejected', uncertain=method=='execute')
                if response.headers.get('content-encoding','identity') != 'identity':
                    raise BridgeFailure('bridge_encoding_rejected', uncertain=method=='execute')
                data = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=4096):
                    data.extend(chunk)
                    if len(data) > 1_000_000:
                        raise BridgeFailure('bridge_response_limit', uncertain=method=='execute')
                result = json.loads(data)
                if not isinstance(result, dict) and not (method=='status' and result is None):
                    raise ValueError('unexpected shape')
                return result
