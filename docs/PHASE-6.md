# Phase 6 — native quality candidate

Phase 6 passed its declared native quality gate on 2026-10-12. The evaluation
used the pinned local Ollama 0.40.3 runtime and Qwen3 4B Q4 model inside a
Linux loopback-only namespace. The assistant combines authorized keyword
retrieval, native model selection, deterministic completion of exact source
clauses, and validation of tenant, document version, page and text span. Outputs
are cited excerpts or review/abstention states; extraction and checklist drafts
still require operator approval. No hosted inference or Odoo write was used.

The final held-out corpus has nine synthetic PDFs from eight independent
document families, two clients and English/Indonesian sources. It was checked
against development and five regression corpora for shared document IDs,
families, PDF hashes and source sentences. Its 13 cases include scope,
exclusions, SLA, procedures, missing/conflicting/expired evidence, a poor scan,
cross-client access and an injection attempt. Source-derived labels and corpus
hashes are in `evaluation/heldout-v6/`; the exact report and split denominators
are in `local/phase-6/final-8/heldout-v6-native.json` and
`local/phase-6/quality-summary.json`.

On that held-out set, the final pipeline achieved 14/14 required extraction
fields, 4/4 documents with all required fields, 7/7 answerable tasks, 10/10
relevant locations retrieved in the first five results, 28/28 correct
citations and supported claims, and 6/6 review/abstention cases. All 13 case
outcomes passed, including the cross-client and injection checks. Observed
cross-client disclosures, unauthorized writes, duplicate effects and false
successes were zero in the declared suite. Each of the six development and
regression splits also passed the same frozen rubric. Their combined counts
were 86/86 fields, 24/24 complete documents, 43/43 answerable tasks, 61/61
retrieval locations and 175/175 citations and supported claims. These are
synthetic lab results, not customer or production accuracy estimates.

The keyword/source-search baseline found 10/10 labeled held-out locations
using the same authorized corpus and queries; it does not generate answers,
checklist drafts or abstention decisions. No comparative answer-quality or
time-saving claim is inferred from that source-search baseline.

Held-out native assistant latency was p50 5.391 s, p90 8.142 s and p95 8.544 s
over 17 tasks; in-memory search p95 was 0.002 s over 13 queries. There were no
run errors. Sequential task throughput was 13.174/min over 77.424 task
seconds, with 0.001 s preflight queue wait; this does not measure concurrent
load. The seven-split supervisor ran for 557.318 s and sampled a peak process
tree RSS of 0.927 GiB, minimum Linux free RAM of 5.462 GiB, and minimum GPU
free memory of 1765 MiB at 0.5 s intervals. Those samples are not hard peak
bounds and exclude a persistent database/full stack. Separate two-page native
Tesseract evidence measured 1.431 and 1.345 s/page for English and Indonesian
machine-rendered scans; scan-quality generalization is unproven. The poor-scan
case is routed to review rather than treated as a successful extraction.

The native quality candidate and application-only v6 bundle are pinned in
`local/phase-6/candidate-freeze.json`. The application bundle is paired with
the verified Phase 5 dependency/model assets; a complete release assembly
still needs Phase 7 acceptance. Phase 7 must validate PostgreSQL/pgvector
durability and RLS, real Odoo #2 two-company save/read-back and recovery,
full-stack blocked-egress cold start, service restart/restore, and repeated
quality/ACL plus normal/peak/soak load against
`config/phase7-resource-budget.json`. Native in-memory latency and sampled
resources do not establish container, database or production SLOs.
