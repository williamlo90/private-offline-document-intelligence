"""Run frozen held-out labels through the persistent offline HTTP stack."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import statistics
import time

import httpx

ROOT = Path('/app/evaluation/heldout-v6')
BASE = 'http://127.0.0.1:8077'


def norm(value: str) -> str:
    return ' '.join(value.casefold().split())


def quantile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower), 3)


def main() -> None:
    manifest = json.loads((ROOT / 'manifest.json').read_text())
    expected = json.loads((ROOT / 'expected.json').read_text())
    extraction = json.loads((ROOT / 'extraction-expected.json').read_text())
    identities = json.loads(Path('/run/secrets/lab-identities.json').read_text())
    tokens = {row['id']: row['token'] for row in identities['actors']}
    rows = []
    times = []
    search_times = []
    citations = 0
    exact = 0
    relevant = 0
    leakage = 0
    errors = 0
    with httpx.Client(base_url=BASE, timeout=145, trust_env=False) as client:
        def request(tenant: str, method: str, path: str, **kwargs):
            headers = {'Authorization': 'Bearer ' + tokens[tenant + '-technician'],
                       **kwargs.pop('headers', {})}
            response = client.request(method, path, headers=headers, **kwargs)
            if response.status_code >= 400:
                raise RuntimeError(f'{method} {path}: {response.status_code} {response.text[:120]}')
            return response.json()

        for item in manifest['documents']:
            path = ROOT / item['file']
            data = path.read_bytes()
            assert hashlib.sha256(data).hexdigest() == item['sha256']
            existing = client.get('/documents/' + item['id'],
                                  headers={'Authorization': 'Bearer ' + tokens[item['tenant'] + '-technician']})
            if existing.status_code == 404:
                document = request(item['tenant'], 'POST', '/pdf-documents',
                                   params={'identifier': item['id'], 'title': item['id'],
                                           'family': item['family'], 'language': item['language'],
                                           'effective': item['effective'], 'expires': item['expires']},
                                   content=data, headers={'Content-Type': 'application/pdf'})
            else:
                assert existing.status_code == 200, existing.status_code
                document = existing.json()
            assert document['digest'] == item['sha256'] and document['family'] == item['family']
            wrong_tenant = 'birch' if item['tenant'] == 'atlas' else 'atlas'
            forbidden = client.get('/documents/' + item['id'],
                                   headers={'Authorization': 'Bearer ' + tokens[wrong_tenant + '-technician']})
            assert forbidden.status_code in (403, 404)
            print('verified', item['id'], flush=True)

        for case in expected['cases']:
            started = time.monotonic()
            hits = request(case['tenant'], 'GET', '/search', params={'q': case['question']})
            search_times.append(time.monotonic() - started)
            labeled = {(identifier, page) for identifier, page, _ in case['evidence']}
            observed = {(hit['document_id'], hit['page']) for hit in hits}
            started = time.monotonic()
            try:
                answer = request(case['tenant'], 'POST', '/skills/answer_client_question',
                                 json={'question': case['question']})
                error = None
            except Exception as exc:
                answer, error = None, str(exc)[:180]
                errors += 1
            elapsed = round(time.monotonic() - started, 3)
            times.append(elapsed)
            excerpts = [] if answer is None else answer['excerpts']
            joined = norm(' '.join(row['value'] for row in excerpts))
            forbidden = sum(norm(value) in joined for value in case.get('forbidden', []))
            for excerpt in excerpts:
                evidence = excerpt['evidence']
                source = request(case['tenant'], 'GET',
                                 f"/documents/{evidence['document_id']}/versions/{evidence['version']}")
                page = next(page for page in source['pages'] if page['number'] == evidence['page'])
                same = (source['digest'] == excerpt['source_sha256'] and
                        page['text'][evidence['start']:evidence['end']] == evidence['quote'] == excerpt['value'])
                citations += 1
                exact += int(same)
                relevant += int(same and (evidence['document_id'], evidence['page']) in labeled)
                forbidden += int(source['tenant'] != case['tenant'])
            leakage += forbidden
            if case['status'] == 'answered':
                passed = (answer is not None and answer['status'] == 'sourced_excerpts' and
                          all(norm(value) in joined for value in case['required']) and
                          bool(excerpts) and forbidden == 0 and
                          all((row['evidence']['document_id'], row['evidence']['page']) in labeled for row in excerpts))
            else:
                required_status = 'abstain' if case['status'] == 'missing' else 'review'
                passed = answer is not None and answer['status'] == required_status and forbidden == 0
            row = {'id': case['id'], 'category': case['category'], 'expected_status': case['status'],
                   'observed_status': None if answer is None else answer['status'], 'passed': passed,
                   'answer_seconds': elapsed, 'retrieval_labeled': len(observed & labeled),
                   'retrieval_total': len(labeled), 'excerpt_count': len(excerpts),
                   'forbidden_disclosures': forbidden, 'error': error}
            rows.append(row)
            print(json.dumps(row), flush=True)

        fields_correct = fields_total = docs_correct = 0
        extraction_rows = []
        for case in extraction['documents']:
            started = time.monotonic()
            answer = request(case['tenant'], 'POST', '/skills/extract_service_terms',
                             json={'document_id': case['document_id'], 'version': 1})
            elapsed = round(time.monotonic() - started, 3)
            times.append(elapsed)
            checks = [any(row['kind'] == field['kind'] and row['evidence']['page'] == field['page'] and
                          norm(field['value']) in norm(row['value']) for row in answer['excerpts'])
                      for field in case['fields']]
            fields_correct += sum(checks)
            fields_total += len(checks)
            docs_correct += int(all(checks))
            extraction_rows.append({'id': case['document_id'], 'correct': sum(checks),
                                    'total': len(checks), 'seconds': elapsed})
            print(json.dumps(extraction_rows[-1]), flush=True)

    answerable = [r for r in rows if r['expected_status'] == 'answered']
    uncertain = [r for r in rows if r['expected_status'] != 'answered']
    retrieval_n = sum(r['retrieval_total'] for r in rows)
    metrics = {'answerable_completion': [sum(r['passed'] for r in answerable), len(answerable)],
               'uncertainty_handling': [sum(r['passed'] for r in uncertain), len(uncertain)],
               'retrieval_recall_at_5': [sum(r['retrieval_labeled'] for r in rows), retrieval_n],
               'field_correctness': [fields_correct, fields_total],
               'document_all_fields': [docs_correct, len(extraction_rows)],
               'citation_exact': [exact, citations], 'citation_relevant': [relevant, citations]}
    report = {'status': 'passed' if all(r['passed'] for r in rows) and not errors and not leakage else 'failed',
              'profile': 'four-container offline Linux stack, frozen heldout-v6 synthetic corpus',
              'cases': len(rows), 'extraction_documents': len(extraction_rows), 'metrics': metrics,
              'latency_seconds': {'n': len(times), 'p50': quantile(times, .5),
                                  'p90': quantile(times, .9), 'p95': quantile(times, .95),
                                  'search_n': len(search_times), 'search_p95': quantile(search_times, .95)},
              'errors': errors, 'forbidden_disclosures': leakage,
              'rows': rows, 'extraction_rows': extraction_rows,
              'limitations': ['Persistent lab also contains prior development and acceptance fixtures',
                              'Inference is native Ollama with deterministic source-clause completion']}
    Path('/tmp/phase7-heldout.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'metrics': metrics, 'latency_seconds': report['latency_seconds']}), flush=True)


if __name__ == '__main__':
    main()
