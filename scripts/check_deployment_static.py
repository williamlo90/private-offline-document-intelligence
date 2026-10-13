"""Syntax-only checks; never invokes Docker or a database."""
import json
from pathlib import Path
from pglast import parse_sql
import yaml

root = Path(__file__).resolve().parents[1]
migrations = {path.name: len(parse_sql(path.read_text(encoding='utf-8')))
              for path in sorted((root / 'migrations').glob('*.sql'))}
compose = yaml.safe_load((root / 'deploy/compose.yaml').read_text(encoding='utf-8'))
assert compose['name'] == 'private-documents-lab'
for service in compose['services'].values():
    assert service['profiles']
    assert service['mem_limit'] and service['cpus']
    assert all(port.startswith('127.0.0.1:') for port in service.get('ports', []))
assert compose['services']['api']['read_only']
dockerfile = (root / 'deploy/Dockerfile').read_text(encoding='utf-8')
assert 'USER app' in dockerfile
assert 'COPY . .' not in dockerfile
result = {'status': 'passed', 'sql_statement_count': sum(migrations.values()), 'migrations': migrations, 'compose_yaml': 'parsed',
          'scope': 'PostgreSQL syntax, YAML shape and selected static safeguards only',
          'not_validated': ['DDL execution', 'RLS behavior', 'transactions', 'image build', 'container runtime'],
          'docker_commands_executed': 0}
target = root / 'local/phase-1/static-deployment.json'
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result))
