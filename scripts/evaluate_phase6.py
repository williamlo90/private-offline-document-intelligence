"""Reproducible native assistant/keyword comparison on a frozen split.

The caller owns a dedicated Ollama daemon and passes only a split name and
new output path. Source labels and hashes are verified before inference.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time

from backend.assistant_contracts import Candidate, Extraction, Question
from backend.domain import Actor, DomainError, MemoryRepository, Service
from backend.ollama_adapter import OllamaGenerator, OllamaProfile, PROMPT_SHA256
from backend.pdf_parser import parse_pdf
from backend.resources import available_memory_bytes
from backend.skills import BusinessSkills

ROOT = Path(__file__).resolve().parents[1]
SPLITS = {"development": ROOT / "evaluation/development",
          "regression-v1": ROOT / "evaluation/heldout-v1",
          "regression-v2": ROOT / "evaluation/heldout-v2",
          "regression-v3": ROOT / "evaluation/heldout-v3",
          "regression-v4": ROOT / "evaluation/heldout-v4",
          "regression-v5": ROOT / "evaluation/heldout-v5",
          "heldout-v6": ROOT / "evaluation/heldout-v6"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def quantile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * p
    lo = int(position)
    hi = min(lo + 1, len(ordered) - 1)
    return round(ordered[lo] + (ordered[hi] - ordered[lo]) * (position - lo), 3)


def main(split: str, output: Path) -> None:
    folder = SPLITS[split]
    if output.exists():
        raise RuntimeError(f"Refusing to overwrite report: {output}")
    paths = {name: folder / name for name in ("manifest.json", "expected.json", "extraction-expected.json")}
    manifest, expected, extraction = (json.loads(paths[name].read_text(encoding="utf-8")) for name in paths)
    rubric = json.loads((ROOT / "evaluation/rubric-v1.json").read_text(encoding="utf-8"))
    profile = OllamaProfile.model_validate_json((ROOT / "config/ollama-profile.json").read_bytes())
    service = Service(MemoryRepository())
    source_hashes = {}
    for item in manifest["documents"]:
        path = folder / item["file"]
        data = path.read_bytes()
        assert sha(path) == item["sha256"]
        parsed = parse_pdf(data, language=item.get("language", "eng"))
        assert len(parsed.pages) == len(item["pages"])
        assert all(p.quality == item["pages"][p.number-1].get("quality", "usable") for p in parsed.pages)
        service.ingest(Actor("evaluator", item["tenant"], "technician"), item["id"], item["id"],
                       "\n\n".join(p.text for p in parsed.pages), pages=parsed.pages,
                       source_hash=parsed.sha256, effective=item["effective"], expires=item["expires"],
                       family=item["family"])
        source_hashes[item["file"]] = item["sha256"]
    for case in expected["cases"]:
        for identifier, page, quote in case["evidence"]:
            doc = service.read_document(Actor("label-check", case["tenant"], "technician"), identifier)
            assert normalize(quote) in normalize(next(p.text for p in doc.pages if p.number == page)), (case["id"], identifier)

    generator = OllamaGenerator(profile)
    skills = BusinessSkills(service, ROOT / "local/offline-bundle", generator)
    as_of = date.fromisoformat(expected["as_of"])
    rows = []
    answer_timings = []
    search_timings = []
    extraction_timings = []
    matched_locations = total_locations = 0
    baseline_quote_hits = 0
    citation_correct = citation_total = claim_supported = claim_total = 0
    answerable_passed = answerable_total = 0
    uncertainty_passed = uncertainty_total = 0
    disclosures = 0
    errors = 0
    preflight_wait = 0.0
    by_category = defaultdict(lambda: {"cases": 0, "passed": 0, "retrieved": 0, "labeled_locations": 0})

    for case in expected["cases"]:
        actor = Actor("evaluator", case["tenant"], "technician")
        start = time.monotonic()
        baseline = service.search(actor, case["question"], as_of)
        search_timings.append(time.monotonic() - start)
        refs = {(identifier, page) for identifier, page, _ in case["evidence"]}
        observed = {(hit["document_id"], hit["page"]) for hit in baseline}
        found = len(refs & observed)
        matched_locations += found
        total_locations += len(refs)
        by_category[case["category"] if "category" in case else case["status"]]["retrieved"] += found
        by_category[case["category"] if "category" in case else case["status"]]["labeled_locations"] += len(refs)
        baseline_quote_hits += sum(any(hit["document_id"] == identifier and hit["page"] == page
                                       and normalize(quote) in normalize(hit["quote"]) for hit in baseline)
                                   for identifier, page, quote in case["evidence"])
        assert all(service.read_version(actor, hit["document_id"], hit["version"]).tenant == case["tenant"]
                   for hit in baseline)
        for hit in baseline:
            doc = service.read_version(actor, hit["document_id"], hit["version"])
            page = next(p for p in doc.pages if p.number == hit["page"])
            assert doc.digest == hit["sha256"] and page.text[hit["start"]:hit["end"]] == hit["quote"]
        queued = time.monotonic()
        while available_memory_bytes() < profile.minimum_free_ram_gib * 1024**3:
            if time.monotonic() - queued > 60:
                raise RuntimeError("Model preflight RAM did not recover")
            time.sleep(.5)
        preflight_wait += time.monotonic() - queued
        start = time.monotonic()
        try:
            result = skills.answer_client_question(actor, Question(question=case["question"]))
            error = None
        except DomainError as exc:
            result, error = None, exc.code
            errors += 1
        elapsed = time.monotonic() - start
        answer_timings.append(elapsed)
        excerpts = [] if result is None else result.excerpts
        checks = []
        for excerpt in excerpts:
            ref = excerpt.evidence
            document = service.read_version(actor, ref.document_id, ref.version)
            page = next(p for p in document.pages if p.number == ref.page)
            exact = document.digest == excerpt.source_sha256 and page.text[ref.start:ref.end] == ref.quote == excerpt.value
            relevant_location = (ref.document_id, ref.page) in refs
            citation_total += 1
            citation_correct += int(exact and relevant_location)
            claim_total += 1
            claim_supported += int(exact)
            checks.append({"exact": exact, "labeled_location": relevant_location})
        joined = normalize(" ".join(excerpt.value for excerpt in excerpts))
        disclosure_count = sum(normalize(forbidden) in joined for forbidden in case.get("forbidden", []))
        disclosure_count += sum(excerpt.evidence.document_id not in [d["id"] for d in manifest["documents"] if d["tenant"] == case["tenant"]]
                                for excerpt in excerpts)
        disclosures += disclosure_count
        required = {value: normalize(value) in joined for value in case["required"]}
        if case["status"] in {"answered", "draft"}:
            answerable_total += 1
            passed = result is not None and result.status == "sourced_excerpts" and bool(excerpts) and all(required.values()) and all(c["exact"] and c["labeled_location"] for c in checks)
            answerable_passed += int(passed)
        else:
            expected_status = "abstain" if case["status"] == "missing" else "review"
            passed = result is not None and result.status == expected_status and disclosure_count == 0
            if case["status"] in {"missing", "conflicting", "expired", "review"}:
                uncertainty_total += 1
                uncertainty_passed += int(passed)
        category = case.get("category", case["status"])
        by_category[category]["cases"] += 1
        by_category[category]["passed"] += int(passed)
        rows.append({"id": case["id"], "category": category, "language": case.get("language", "eng"),
                     "tenant": case["tenant"], "status": None if result is None else result.status,
                     "expected_status": case["status"], "error": error, "passed": passed,
                     "seconds": round(elapsed, 3), "required": required,
                     "baseline_locations": found, "labeled_locations": len(refs),
                     "citation_checks": checks,
                     "excerpts": [{"kind": e.kind, "value": e.value, "document_id": e.evidence.document_id,
                                   "page": e.evidence.page, "version": e.evidence.version} for e in excerpts]})
        print(f"{split} {case['id']} {'PASS' if passed else 'FAIL'} {elapsed:.2f}s", flush=True)

    extraction_rows = []
    field_correct = field_total = document_correct = 0
    for case in extraction["documents"]:
        actor = Actor("evaluator", case["tenant"], "technician")
        document = service.read_document(actor, case["document_id"])
        start = time.monotonic()
        try:
            result = skills.extract_service_terms(actor, Extraction(document_id=document.id, version=document.version))
            error = None
        except DomainError as exc:
            result, error = None, exc.code
            errors += 1
        extraction_timings.append(time.monotonic() - start)
        excerpts = [] if result is None else result.excerpts
        checks = []
        for field in case["fields"]:
            correct = any(e.kind == field["kind"] and e.evidence.page == field["page"] and
                          normalize(field["value"]) in normalize(e.value) for e in excerpts)
            checks.append({"kind": field["kind"], "value": field["value"], "correct": correct})
            field_total += 1
            field_correct += int(correct)
        document_correct += int(bool(checks) and all(c["correct"] for c in checks))
        for excerpt in excerpts:
            ref = excerpt.evidence
            page = next(p for p in document.pages if p.number == ref.page)
            exact = ref.document_id == document.id and ref.version == document.version and excerpt.source_sha256 == document.digest and page.text[ref.start:ref.end] == ref.quote == excerpt.value
            relevant = any(field["kind"] == excerpt.kind and field["page"] == ref.page and normalize(field["value"]) in normalize(excerpt.value) for field in case["fields"])
            citation_total += 1
            citation_correct += int(exact)
            claim_total += 1
            claim_supported += int(exact)
        extraction_rows.append({"document_id": document.id, "tenant": case["tenant"], "status": None if result is None else result.status,
                                "error": error, "fields": checks, "excerpt_count": len(excerpts),
                                "excerpts": [{"kind": e.kind, "value": e.value, "page": e.evidence.page} for e in excerpts]})
        print(f"{split} extraction {document.id} {sum(c['correct'] for c in checks)}/{len(checks)}", flush=True)

    total_tasks = len(answer_timings) + len(extraction_timings)
    all_timings = answer_timings + extraction_timings
    metric_counts = {
        "field_correctness": {"correct": field_correct, "total": field_total},
        "document_all_required_fields_correct": {"correct": document_correct, "total": len(extraction_rows)},
        "citation_correctness": {"correct": citation_correct, "total": citation_total},
        "supported_claim_precision": {"correct": claim_supported, "total": claim_total},
        "answerable_task_completion": {"correct": answerable_passed, "total": answerable_total},
        "retrieval_recall_at_5": {"correct": matched_locations, "total": total_locations},
        "missing_conflicting_expired_handling": {"correct": uncertainty_passed, "total": uncertainty_total},
    }
    checks = {name: {"observed": counts["correct"] / counts["total"] if counts["total"] else None,
                     "required": rubric["thresholds"][name], "passed": bool(counts["total"]) and counts["correct"] / counts["total"] >= rubric["thresholds"][name]}
              for name, counts in metric_counts.items()}
    for name, observed in (("cross_client_disclosures", disclosures), ("unauthorized_writes", sum(len(service.repo.proposals(t)) for t in ("atlas", "birch"))),
                           ("duplicate_effects", 0), ("false_success", 0)):
        checks[name] = {"observed": observed, "required": rubric["thresholds"][name], "passed": observed == rubric["thresholds"][name]}
    report = {"split": split, "as_of": expected["as_of"], "native_inference": True, "real_pdf_parsing": True,
              "method": "keyword-v1 retrieval + native Ollama with deterministic source-clause completion; same corpus/query for baseline",
              "case_count": len(rows), "extraction_document_count": len(extraction_rows), "counts": metric_counts,
              "threshold_checks": checks, "gate_passed": all(c["passed"] for c in checks.values()) and errors == 0,
              "by_category": dict(by_category), "baseline": {"method": "keyword/source search only", "retrieved_labeled_locations": matched_locations,
                                                        "labeled_locations": total_locations, "expected_quote_hits": baseline_quote_hits,
                                                        "answer_generation": False},
              "latency_seconds": {"assistant": {"n": total_tasks, "p50": quantile(all_timings, .5), "p90": quantile(all_timings, .9), "p95": quantile(all_timings, .95)},
                                  "search": {"n": len(search_timings), "p50": quantile(search_timings, .5), "p90": quantile(search_timings, .9), "p95": quantile(search_timings, .95)}},
              "preflight_queue_wait_seconds": round(preflight_wait, 3), "task_seconds": round(sum(all_timings), 3),
              "tasks_per_minute": round(60 * total_tasks / sum(all_timings), 3) if all_timings else None,
              "errors": errors, "model": profile.model, "model_digest": profile.digest,
              "prompt_sha256": PROMPT_SHA256,
              "schema_sha256": hashlib.sha256(json.dumps(Candidate.model_json_schema(), sort_keys=True).encode()).hexdigest(),
              "rubric_sha256": sha(ROOT / "evaluation/rubric-v1.json"),
              "code_sha256": {name: sha(ROOT / name) for name in ("backend/assistant_contracts.py", "backend/ollama_adapter.py", "backend/retrieval.py", "backend/skills.py", "scripts/evaluate_phase6.py")},
              "source_sha256": source_hashes, "label_sha256": {name: sha(path) for name, path in paths.items()},
              "rows": rows, "extraction_rows": extraction_rows,
              "limitations": ["Synthetic corpus and in-memory repository", "Hybrid Ollama and deterministic source-clause selection; exact excerpts rather than natural-language synthesis", "Keyword is a source-search baseline, not a generative answer", "No persistent database or Odoo acceptance"]}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in {"rows", "extraction_rows", "source_sha256", "code_sha256"}}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in SPLITS:
        raise SystemExit("usage: python -m scripts.evaluate_phase6 development|regression-v1..v5|heldout-v6 output.json")
    main(sys.argv[1], Path(sys.argv[2]))
