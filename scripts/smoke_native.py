"""Start and stop only this project's API; verify a real loopback HTTP workflow."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import Request, urlopen

root = Path(__file__).resolve().parents[1]
profile = root / 'local/lab-identities.json'
config = json.loads(profile.read_text(encoding='utf-8'))
tech = next(a for a in config['actors'] if a['id'] == 'atlas-technician')
with socket.socket() as listener:
    listener.bind(('127.0.0.1', 0))
    port = listener.getsockname()[1]
env = {**os.environ, 'PRIVATE_LAB_CONFIG': str(profile)}
target = root / 'local/phase-1'
target.mkdir(parents=True, exist_ok=True)
with (target / 'native-server.log').open('w', encoding='utf-8') as log:
    process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'backend.main:load_app', '--factory',
                                '--host', '127.0.0.1', '--port', str(port), '--no-access-log'],
                               cwd=root, env=env, stdout=log, stderr=log)
    try:
        deadline = time.monotonic() + 20
        while True:
            try:
                with urlopen(f'http://127.0.0.1:{port}/health', timeout=1) as response:
                    health = json.load(response)
                break
            except OSError:
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError('Native server did not become ready; see local log')
                time.sleep(.1)
        request = Request(f'http://127.0.0.1:{port}/documents', headers={'Authorization': 'Bearer ' + tech['token']})
        with urlopen(request, timeout=3) as response:
            documents = json.load(response)
        assert len(documents) == 6
        assert all(d['tenant'] == 'atlas' for d in documents)
        assert health['persistence'] == 'memory-harness'
        result = {'real_loopback_http': 'passed', 'authorized_documents': len(documents),
                  'health': health, 'process_cleanup': 'owned process only', 'database_acceptance': 'pending Phase 7'}
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
(target / 'native-smoke.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result))
