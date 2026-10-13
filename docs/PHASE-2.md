# Phase 2 - Documents and retrieval (local gate passed)

The local parser accepts PDF bytes through authenticated `POST /pdf-documents`.
It runs in a separate process, checks a 10 MiB input limit, 30-page limit,
200,000-character extracted text limit, OCR render pixel limit and timeouts.
Encrypted and malformed PDFs return sanitized errors. Parsing is limited to one
job per API process; additional jobs receive `parser_busy`. The Windows worker
uses a Job Object with a 512 MiB aggregate committed-memory limit and a maximum
of three processes. Terminating the worker also terminates its OCR descendants.
Failure to establish the boundary rejects parsing. Linux has a per-process
address-space limit and timeout process-group termination prepared, but native
Linux acceptance and multi-process queue coordination remain pending.

Text is extracted per page using pypdf. Pages with little extractable text go to
local PDFium and Tesseract. OCR confidence below 65 or insufficient text marks a
page for review; this is a heuristic, not a guarantee of scan correctness. Set
`PRIVATE_TESSDATA` to the project's `local/ocr/tessdata` for the provisioned English
and Indonesian language assets. `PRIVATE_TESSERACT` optionally selects the binary.
No hosted fallback exists. Provisioning is separate from offline acceptance.

Documents now retain page provenance, source hashes, effective/expiry dates and
immutable historical versions in the memory harness. Keyword retrieval returns
page/chunk offsets, exact excerpts, version/hash and active/expired/future/conflict
status. Every call filters current permissions and skips deleted documents;
there is no shared retrieval cache yet. Historical reads require current access.
Authenticated actors come from the server profile. Administrators can revoke and
restore document access for an existing same-tenant identity. Revocation applies
to already-active sessions, historical reads, search, proposals and overwrites.
Affected proposals become permanently stale; restoring access does not revive
their previous approval. Restore cannot widen the original profile grant.
Persistent indexes remain pending.

Checklist proposals bind each step to a source page and exact character offsets.
Expired, poor-quality and known conflicting sources cannot create a proposal.
Approval rechecks source versions, dates and newly introduced conflicts.
The UI submits the version it displayed when preparing a checklist; the domain
rejects a changed version instead of silently using unseen content.

The React workspace now accepts PDF uploads, displays extracted pages and source
dates, and searches authorized evidence with version/page references and status.
Opening a search result checks the current version again. File limits and parser
errors are shown without exposing internal exception data.
Denied requests (401/403/404) clear the mounted workspace and require sign-in
again. Refresh clears the displayed source, draft steps, search results and
review queue before fetching current permissions. Native browser checks revoke
access through the administrative API and verify both denied-source navigation
and a successful filtered refresh remove stale content. The UI does not receive
revocation push events; already displayed content is cleared on these checks.

The service-term contract covers coverage, exclusions, procedures, obligations
and SLA values. Every extracted value must occur in its exact, authorized
page/offset quotation. This extractive validator checks evidence integrity; it
does not claim legal interpretation or correct semantic classification.

## Validated evidence (2026-10-12)

- Full backend regression: 130 tests passed, including real-tokenizer padding,
  native-index access/version/deletion contracts and authenticated semantic
  endpoint checks. The native index and the keyword baseline share exact page
  chunks and status rules.
- Native Tesseract recovered the expected phrases from two synthetic scanned
  PDFs: English in 1.431 seconds and Indonesian in 1.345 seconds under the
  production Windows resource boundary. This is a two-fixture smoke test.
- Keyword baseline on 13 development cases: 11/11 labeled locations retrieved
  in the first five results, 11/11 expected quotes covered and 26/26 returned
  excerpts matching their source spans. Only 11/26 locations match the limited
  reference labels; this is not exhaustive relevance precision. Three cases
  without labeled support still return hits, so a hit is not an answer.
- ONNX Runtime, tokenizers and NumPy are installed in the isolated virtual
  environment and pinned in requirements.lock; pip check passes. Seven local
  embedding assets pass SHA256 verification against their provisioning manifest.
  The quantized ONNX model is 118,453,870 bytes; no hosted inference is used.
- Parameterized pgvector read/replace/delete contracts enforce tenant, grants,
  source version/hash, exact spans and embedding revision. Transaction doubles
  and SQL syntax checks pass; real database behavior awaits Phase 7 acceptance.

Evidence is retained locally in `local/phase-2/`: `resumed-tests.xml`,
`tokenizer-vector-tests.xml`, `native-ocr.json`, `keyword-baseline.json`,
`embedding-provisioning.json`, `embedding-smoke-result.json`,
`embedding-corpus-profile-result.json`, `embedding-corpus-result.json` and
`phase2-regression.xml`.

## Native embedding and retrieval evidence

The pinned candidate is multilingual MiniLM-L12-v2, revision
`e8f8c211226b894fcb81acc59f3b34ba3efd5f42`, with the official AVX2 quantized
ONNX export, Apache-2.0 license and 384-dimensional mean-pooled embeddings.
Native inference passed a three-text multilingual smoke: 384 dimensions,
related English/Indonesian cosine 0.659 versus unrelated −0.016. Worker RSS
after load and inference was 0.421–0.424 GiB in two runs. The measured load
preflight is now 1.75 GiB, retaining a 1 GiB host reserve and margin; the
6 GiB generative-model budget is separate. The supervisor counts the Windows
virtual-environment launcher and its interpreter child, samples every 50 ms,
and stops the owned tree above 1 GiB sampled RSS, below 1 GiB host reserve or
after 120 seconds. Samples can miss brief peaks.

`GET /semantic-search` uses the pinned local model and an in-memory index,
checking current actor grants, tenant, source version, hash, page quote and
deletion on each search. Real pgvector execution belongs to Phase 7. The
native 13-case development evaluation passed: 11/11 expected document/page
locations and quotes in the first five, 61/61 returned exact source spans,
and a real authenticated HTTP call to `/semantic-search` returned 200. The
owned process tree peaked at 0.463 GiB sampled RSS; host free memory reached
1.382 GiB at its lowest sample. These outcomes prove the Phase 2 retrieval
path on this small corpus, not generated answer quality.

Provisioning streams files without loading model tensors and uses a separate
0.5 GiB free-memory guard. The small development corpus cannot establish
held-out generalization, answer correctness or offline delivery. Semantic
search can return hits for questions without supporting evidence; abstention
is a Phase 3 assistant requirement. The AI loop remains paused.
