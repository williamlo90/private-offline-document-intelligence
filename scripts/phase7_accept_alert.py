"""Prove the local reviewer queue delivers actionable source alerts offline."""
import json
from pathlib import Path
import socket

import httpx


def main():
    actors = json.loads(Path('/run/secrets/lab-identities.json').read_text())['actors']
    tokens = {a['id']: a['token'] for a in actors}
    with socket.socket() as sock:
        sock.settimeout(2)
        try:
            sock.connect(('1.1.1.1', 443))
        except OSError as error:
            assert error.errno == 101
        else:
            raise AssertionError('External TCP reachable')
    with httpx.Client(base_url='http://127.0.0.1:8077', timeout=10, trust_env=False) as client:
        queues = {}
        for tenant in ('atlas', 'birch'):
            result = client.get('/source-reviews',
                                headers={'Authorization': 'Bearer ' + tokens[tenant + '-reviewer']})
            assert result.status_code == 200
            queues[tenant] = result.json()
        assert any(row['document_id'] == 'birch-illegible-ticket' and 'poor_ocr' in row['reasons']
                   for row in queues['birch'])
        assert any(row['document_id'] == 'atlas-exception-a' and 'conflicting' in row['reasons']
                   for row in queues['atlas'])
        assert all(not row['document_id'].startswith('birch-') for row in queues['atlas'])
        assert all(not row['document_id'].startswith('atlas-') for row in queues['birch'])
    evidence = {'status': 'passed', 'delivery': 'reviewer read local /source-reviews queue',
                'reviewers': 2, 'atlas_alerts': len(queues['atlas']),
                'birch_alerts': len(queues['birch']), 'poor_ocr_received': True,
                'conflict_received': True, 'cross_tenant_alerts': 0,
                'offline_external_tcp_blocked': True,
                'limitation': 'Pull-based local UI queue; no push notification or operator acknowledgement'}
    Path('/tmp/phase7-alert.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps(evidence))


if __name__ == '__main__':
    main()
