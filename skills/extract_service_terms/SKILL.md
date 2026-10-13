# extract_service_terms - contract 1.0

Owner: MSP service manager. Purpose: select coverage, exclusions, procedures, obligations and sla excerpts.
Binding: `backend.skills.BusinessSkills.extract_service_terms`; HTTP POST `/skills/extract_service_terms`.
Input: document_id and the reviewed version. Input/output schemas are in `schema.json`.

Only authenticated technicians/service managers with current document grants
may invoke the capability. Identity comes from the transport, not the payload.
The shared source assistant retrieves authorized evidence, rejects known source
conflicts, expired/future or poor-OCR sources into review with document ID,
version and reason. Extraction requires the current reviewed version.

The model adapter may select exact spans and term categories or abstain. It
cannot author free-form claims, source identifiers, actions or approval state.
The server reconstructs quoted text, offsets, version and SHA-256. It rechecks
current authorized documents after generation; changed versions, revocations
and new visible conflicts fail closed. Output is read-only and always requires
review. Exact quotation does not establish relevance, complete context, correct
classification or entailment: those remain native-model evaluation gates.

Limits: at most 24,000 source characters, 100 evidence entries and 30 output
spans, each up to 2,000 characters. Context overflow produces review instead of
silent truncation. Keyword retrieval selects at most five hits for questions;
it does not prove missing evidence elsewhere in the corpus. Cancellation is
checked before/after generation, with no retries. Extraction presents each
source sentence as separate evidence. The local Ollama adapter enforces timeout
and resource preflight/reserve. No external writes, downloads or fallback.

Status: native Ollama development evaluation passed with the opt-in pinned
profile in `docs/PHASE-3.md`. Without that profile and its project-owned daemon,
generation returns `native_model_unavailable` (503). Held-out quality, full UI
presentation and MCP/worker consumption remain later gates.
Compatibility: 1.0 introduces source-selection contracts only.
