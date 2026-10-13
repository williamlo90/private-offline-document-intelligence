"""Generate untracked local identities. Does not print credentials or overwrite them."""
import json
from pathlib import Path
import secrets

root = Path(__file__).resolve().parents[1]
path = root / 'local/lab-identities.json'
path.parent.mkdir(parents=True, exist_ok=True)
actors = [{'id': f'{tenant}-{role}', 'tenant': tenant, 'role': role, 'token': secrets.token_urlsafe(32)}
          for tenant in ('atlas', 'birch')
          for role in ('technician', 'service_manager', 'administrator', 'auditor')]
with path.open('x', encoding='utf-8') as stream:
    json.dump({'profile': 'native-memory-harness', 'actors': actors}, stream, indent=2)
print('Created local/lab-identities.json; credentials not printed. Memory state resets on restart.')
