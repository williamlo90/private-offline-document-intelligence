"""Bounded one-user and two-user load against the offline persistent API."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import time

import httpx

BASE = 'http://127.0.0.1:8077'


def q(values, p):
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * p
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower), 3)


def main():
    actors = json.loads(Path('/run/secrets/lab-identities.json').read_text())['actors']
    tokens = {a['id']: a['token'] for a in actors}
    rows = []
    memory = []

    def queue_waits():
        with httpx.Client(base_url=BASE, timeout=10, trust_env=False,
                          headers={'Authorization': 'Bearer ' + tokens['atlas-administrator']}) as client:
            response = client.get('/runtime-metrics')
            assert response.status_code == 200
            return response.json()['inference_queue_wait_seconds']

    initial_queue_count = len(queue_waits())

    def request(actor, path, *, method='GET', body=None, profile='normal'):
        started = time.monotonic()
        with httpx.Client(base_url=BASE, timeout=145, trust_env=False,
                          headers={'Authorization': 'Bearer ' + tokens[actor]}) as client:
            response = client.request(method, path, json=body)
        elapsed = time.monotonic() - started
        for meter in (Path('/sys/fs/cgroup/memory.current'), Path('/sys/fs/cgroup/memory/memory.usage_in_bytes')):
            if meter.exists():
                memory.append(int(meter.read_text()))
                break
        row = {'profile': profile, 'path': path, 'actor': actor, 'seconds': round(elapsed, 3),
               'http': response.status_code}
        rows.append(row)
        if response.status_code != 200:
            raise AssertionError(row)
        return response.json()

    started = time.monotonic()
    for _ in range(20):
        request('atlas-technician', '/search?q=resolver+maintenance+ticket')
    for _ in range(3):
        answer = request('atlas-technician', '/skills/answer_client_question', method='POST',
                         body={'question': 'What is the urgent stale-signature acknowledgement target?'})
        assert answer['status'] == 'sourced_excerpts'
    normal_seconds = time.monotonic() - started
    print(json.dumps({'stage': 'normal', 'requests': len(rows), 'seconds': round(normal_seconds, 3)}), flush=True)

    peak_started = time.monotonic()
    peak_answers = []
    for _ in range(2):
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(request, actor, '/skills/answer_client_question', method='POST',
                                   body={'question': question}, profile='peak')
                       for actor, question in (
                           ('atlas-technician', 'What are the resolver change desk steps and safety prohibition?'),
                           ('birch-technician', 'What is the critical offline-scanner initial response target?'))]
            peak_answers.extend(future.result() for future in futures)
    assert all(a['status'] == 'sourced_excerpts' for a in peak_answers)
    peak_seconds = time.monotonic() - peak_started
    print(json.dumps({'stage': 'peak', 'seconds': round(peak_seconds, 3),
                      'verified': all(a['status'] == 'sourced_excerpts' for a in peak_answers)}), flush=True)

    groups = {}
    for name in ('normal', 'peak'):
        sample = [row['seconds'] for row in rows if row['profile'] == name]
        groups[name] = {'n': len(sample), 'p50': q(sample, .5), 'p90': q(sample, .9),
                        'p95': q(sample, .95), 'errors': sum(row['http'] != 200 for row in rows if row['profile'] == name)}
    searches = [row['seconds'] for row in rows if row['path'].startswith('/search')]
    answer_times = [row['seconds'] for row in rows if row['path'].startswith('/skills/answer')]
    observed_queue_waits = queue_waits()[initial_queue_count:]
    assert len(observed_queue_waits) == len(answer_times)
    result = {'status': 'passed' if max(searches) <= 2 and q(answer_times, .95) <= 90
              and max(observed_queue_waits) <= 60 else 'failed',
              'normal_users': 1, 'peak_users': 2, 'inference_concurrency_configured': 1,
              'soak_window_seconds': 0,
              'measurements': groups,
              'search': {'n': len(searches), 'p50': q(searches, .5), 'p90': q(searches, .9),
                         'p95': q(searches, .95)},
              'answer': {'n': len(answer_times), 'p50': q(answer_times, .5), 'p90': q(answer_times, .9),
                         'p95': q(answer_times, .95)},
              'throughput_requests_per_second': round(len(rows) / (normal_seconds + peak_seconds), 3),
              'api_cgroup_peak_bytes_sampled': max(memory) if memory else None,
              'errors': sum(row['http'] != 200 for row in rows),
              'queue_wait_seconds': {'n': len(observed_queue_waits), 'p50': q(observed_queue_waits, .5),
                                     'p90': q(observed_queue_waits, .9), 'p95': q(observed_queue_waits, .95),
                                     'max': max(observed_queue_waits)},
              'verified_completion': all(a['status'] == 'sourced_excerpts' for a in peak_answers),
              'limitations': ['Synthetic workload', 'No soak test in revised portfolio gate',
                              'GPU VRAM and other containers require separate host sampling']}
    Path('/tmp/phase7-load.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
