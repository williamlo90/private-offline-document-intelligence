# Phase 3 — local assistant and executable skills

**Gate passed on the local development harness (2026-10-12).** One pinned
Ollama 0.40.3/Qwen3 4B Instruct Q4_K_M model ran native on the synthetic PDFs.
The four skills share domain rules for authorization, source versioning, review
and audit. `answer_client_question` and `extract_service_terms` used native
inference; `prepare_service_checklist` and `audit_offline_readiness` are
executable deterministic skills. All four have schemas and tests.

The frozen Phase 0 rubric was checked on 13 answer cases and four extraction
documents (16 required fields). Native results: 8/8 answerable cases complete,
16/16 extraction fields, 4/4 documents with every required field, 24/24 exact
citations and supported claims, and 4/4 missing/conflicting/expired cases
handled. Cross-client disclosure and unauthorized writes were zero on this
declared suite. Retrieval recall at five was 11/11 from the preceding native
Phase 2 evaluation. There were 17 timed tasks, p95 7.182 seconds, and 1.002
seconds total preflight RAM queue wait. The supervised run lasted 87.925 seconds;
sampled peak owned process RSS was 1.619 GiB, minimum host free RAM 1.244 GiB,
and minimum GPU free memory 1662 MiB. The adapter's 1.75 GiB preflight and
1 GiB runtime reserve were not lowered. The 100 ms samples and GPU snapshots
are observations, not hard OS allocation limits.

An authenticated FastAPI skill smoke with the real model returned a cited
60-minute SLA clause. Anonymous access was denied; a separate tenant received
no Atlas fact; no proposal was written. Adapter/contract tests cover malformed
or invented selections, source changes, injection, timeout, memory limits,
digest mismatch, and uncertain-generation recovery. Backend regression:
137 passed.

Reproduce with the commands in [local inference](LOCAL-INFERENCE.md). Exact
model, prompt, schema and rubric pins are in
[ollama-runtime-lock.json](../config/ollama-runtime-lock.json); detailed per-case
native reports and raw synthetic selections are in ignored `local/phase-3/`.
The development set guided prompt repair, so these results do not establish
held-out generalization. Offline egress, PostgreSQL, Odoo and container/Linux
acceptance remain later gates.
