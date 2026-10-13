"""Project-owned Linux lab crash, restore and bounded fault drills."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / 'local/phase-7'
PROJECT = 'private-documents-phase7'
API = PROJECT + '-api-1'
DB = PROJECT + '-database-1'
IMAGE = 'private-documents-api:phase7'
COMPOSE = ['docker', 'compose', '-f', str(ROOT / 'deploy/compose.yaml'),
           '-f', str(ROOT / 'deploy/compose.offline.yaml'), '-p', PROJECT,
           '--env-file', str(LOCAL / 'compose.env'), '--profile', 'data-acceptance',
           '--profile', 'platform-acceptance', '--profile', 'full-stack']


def run(*args, check=True):
    return subprocess.run(args, text=True, capture_output=True, check=check)


def owned(name):
    result = run('docker', 'inspect', '--format', '{{index .Config.Labels "com.docker.compose.project"}}', name)
    assert result.stdout.strip() == PROJECT


def api_probe():
    code = ("import json,httpx; from pathlib import Path; "
            "a=json.loads(Path('/run/secrets/lab-identities.json').read_text()); "
            "t=next(x['token'] for x in a['actors'] if x['id']=='atlas-technician'); "
            "c=httpx.Client(timeout=10,trust_env=False,headers={'Authorization':'Bearer '+t}); "
            "h=c.get('http://127.0.0.1:8077/health'); "
            "d=c.get('http://127.0.0.1:8077/documents/atlas-edr-freshness'); "
            "assert h.status_code==200 and d.status_code==200 and d.json()['version']==1; "
            "print(json.dumps({'health':h.json()['status'],'document_version':d.json()['version']}))")
    return json.loads(run('docker', 'exec', API, 'python', '-c', code).stdout)


def main():
    for name in (API, DB, PROJECT + '-odoo-1', PROJECT + '-ollama-1'):
        owned(name)
    before = api_probe()
    run('docker', 'kill', API)
    run(*COMPOSE, 'up', '-d', '--no-deps', 'api')
    for attempt in range(20):
        try:
            after = api_probe()
            break
        except (subprocess.CalledProcessError, ValueError):
            if attempt == 19:
                raise
            time.sleep(1)
    assert before == after

    backup = '/tmp/phase7-final-restore.dump'
    restored = 'private_documents_phase7_recovery'
    run('docker', 'exec', DB, 'pg_dump', '-Fc', '-U', 'private_documents_owner',
        '-d', 'private_documents_lab', '-f', backup)
    run('docker', 'exec', DB, 'createdb', '-U', 'private_documents_owner', restored)
    try:
        run('docker', 'exec', DB, 'pg_restore', '-U', 'private_documents_owner',
            '-d', restored, backup)
        query = "SELECT count(*) FROM documents;"
        count = int(run('docker', 'exec', DB, 'psql', '-U', 'private_documents_owner',
                        '-d', restored, '-tAc', query).stdout.strip())
        assert count >= 10
    finally:
        run('docker', 'exec', DB, 'dropdb', '-U', 'private_documents_owner', restored)

    disk_code = ("import errno; from pathlib import Path; "
                 "p=Path('/fault/probe'); "
                 "\ntry: p.write_bytes(b'x'*(2*1024*1024)); raise AssertionError('write succeeded')"
                 "\nexcept OSError as e: assert e.errno==errno.ENOSPC; print('ENOSPC observed')")
    disk = run('docker', 'run', '--rm', '--network', 'none', '--tmpfs', '/fault:rw,size=1m',
               '--entrypoint', 'python', IMAGE, '-c', disk_code)
    assert 'ENOSPC observed' in disk.stdout
    oom = run('docker', 'run', '--rm', '--network', 'none', '--memory', '64m',
              '--memory-swap', '64m', '--entrypoint', 'python', IMAGE,
              '-c', 'x=bytearray(256*1024*1024); print(len(x))', check=False)
    assert oom.returncode in (137, -9), (oom.returncode, oom.stderr[:200])

    evidence = {'status': 'passed', 'lab': PROJECT, 'linux_containers': 4,
                'api_process_killed_and_restarted': True,
                'persistent_document_read_after_crash': after,
                'db_backup_restored_document_count': count,
                'disk_full': 'ENOSPC in disposable container tmpfs; application service not filled',
                'oom': 'disposable API-image process killed by 64MiB cgroup',
                'host_reboot': False, 'lab_vm_reboot': False,
                'limitations': ['Faults isolated to disposable container, not full-stack failure injection',
                                'No VM reboot; restart of project-owned Compose lab is a separate acceptance']}
    (LOCAL / 'operations-drills.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps(evidence))


if __name__ == '__main__':
    main()
