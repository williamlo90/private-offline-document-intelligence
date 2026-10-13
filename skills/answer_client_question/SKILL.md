# answer_client_question - contract 1.0

Owner: MSP service manager. Purpose: select source excerpts relevant to a client question.
Binding: `backend.skills.BusinessSkills.answer_client_question`; HTTP POST `/skills/answer_client_question`.
Input: question (1-1000 characters). Input/output schemas are in `schema.json`.

Only authenticated technicians/service managers with current document grants
may invoke the capability. Identity comes from the transport, not the payload.
The shared source assistant retrieves authorized evidence, rejects known source
conflicts, expired/future or poor-OCR sources into review with document ID,
version and reason, and abstains when no keyword evidence exists.

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
checked before/after generation, with no retries. The local Ollama adapter
enforces timeout and resource preflight/reserve; the supervised lab owns and
can stop its daemon. No external writes, downloads or fallback.

Status: native Ollama development evaluation and authenticated API smoke passed
with the opt-in pinned profile in `docs/PHASE-3.md`. Without that profile and
its project-owned daemon, generation returns `native_model_unavailable` (503).
Held-out quality, full UI presentation and MCP/worker consumption remain later
gates.
Compatibility: 1.0 introduces source-selection contracts only.
