"""Native Windows resource boundaries, with only test-owned processes."""
import os
from pathlib import Path
import subprocess
import sys
import time

import psutil
import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows job acceptance')


def test_worker_committed_memory_limit():
    result = subprocess.run([sys.executable, '-c', '''
from backend.parser_limits import constrain_worker
constrain_worker(128 * 1024 * 1024)
try:
    allocation = bytearray(256 * 1024 * 1024)
except MemoryError:
    print('allocation-blocked', flush=True)
else:
    raise AssertionError('memory limit was not enforced')
'''], cwd=ROOT, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'allocation-blocked'


def test_killed_worker_terminates_ocr_descendant(tmp_path):
    marker = tmp_path / 'child.pid'
    script = '''
from backend.parser_limits import constrain_worker
from pathlib import Path
import subprocess, sys, time
constrain_worker()
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
Path(sys.argv[1]).write_text(str(child.pid))
time.sleep(60)
'''
    worker = subprocess.Popen([sys.executable, '-c', script, str(marker)], cwd=ROOT)
    child = None
    try:
        deadline = time.monotonic() + 10
        while not marker.exists() and time.monotonic() < deadline and worker.poll() is None:
            time.sleep(.05)
        assert marker.exists(), 'worker did not start the owned child'
        child = psutil.Process(int(marker.read_text()))
        worker.kill()
        worker.wait(timeout=5)
        child.wait(timeout=5)
        assert not child.is_running()
    finally:
        if worker.poll() is None:
            worker.kill()
            worker.wait(timeout=5)
        if child is not None and child.is_running():
            child.kill()
            child.wait(timeout=5)
