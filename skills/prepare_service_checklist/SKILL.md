# Prepare service checklist — contract 1.0

Owner: local MSP service manager. Use to turn operator-selected SOP steps into
a sourced review draft. Do not use to execute IT work, approve a proposal or save
to Odoo. This version validates extractive steps; it does not generate them.

Binding: `backend.skills.BusinessSkills.prepare_service_checklist`.
Transport: `POST /skills/prepare_service_checklist`; the current UI's versioned
`POST /checklists` also uses this binding. Input/output: `schema.json`.

The transport supplies the authenticated actor; payloads cannot override actor,
tenant or role. Technicians and service managers need current source grants.
Supply document IDs, exact source steps and the versions the operator reviewed.
The shared domain checks permissions, versions, dates, OCR quality, conflicts
and exact page spans, then stores a draft awaiting a different manager's review.
Output includes source hashes, versions, page offsets and a payload hash.

Stale, ambiguous, unsupported or unauthorized sources fail without creating a
proposal. There are no external calls or automatic retries. An unknown transport
outcome must be reconciled from the review queue before retrying: this draft
operation is not idempotent. The synchronous local transaction is not interrupted
mid-commit. Input is bounded to 10 documents and 30 steps; database timeouts and
worker cancellation will require transport-level integration.

Validation: `tests/test_skills.py` and existing domain/API suites. This skill is
deterministic and requires no model; MCP/worker consumption remains later work.
Compatibility: 1.0 introduces required expected versions on the skill endpoint;
the legacy manual endpoint retains its previous optional-version contract.
